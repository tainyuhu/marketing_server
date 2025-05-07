# services/order_services.py 

import uuid
import redis
import logging
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError

from ..models import (
    Order, OrderItem, Batch, InventoryReservation, 
    OrderInventoryLog, OrderConfiguration, ProductItemRelation,
    Product, Activity
)
from .simplified_order_services import generate_order_number

logger = logging.getLogger(__name__)

# 創建Redis連接
redis_client = redis.Redis.from_url(settings.REDIS_URL)

class OrderValidationError(Exception):
    """訂單驗證錯誤"""
    pass

class OrderDuplicationError(Exception):
    """訂單重複提交錯誤"""
    pass

def validate_cart_items(cart_items):
    """
    驗證購物車商品
    - 檢查商品是否存在
    - 檢查商品是否上架
    - 檢查商品數量是否符合限制
    - 檢查活動是否有效
    """
    if not cart_items:
        raise OrderValidationError("購物車為空")
    
    for cart_item in cart_items:
        # 檢查商品是否存在
        if not cart_item.product:
            raise OrderValidationError("商品不存在")
        
        product = cart_item.product
        
        # Product 模型沒有 is_active 欄位，但它繼承自 SoftModel，可以用 is_deleted 判斷
        if getattr(product, 'is_deleted', False):
            raise OrderValidationError(f"商品 {product.product_name} 已下架")
        
        # 檢查商品數量限制
        quantity = cart_item.quantity
        if quantity <= 0:
            raise OrderValidationError(f"商品 {product.product_name} 數量必須大於0")
        
        # Product 模型沒有 max_purchase_quantity 欄位，可以跳過此檢查
        
        # 檢查活動有效性（如果有活動）
        if cart_item.activity:
            validate_activity(cart_item.activity, product, quantity)

def validate_activity(activity, product, quantity):
    """
    驗證活動有效性
    """
    now = timezone.now()
    
    # Activity 模型沒有 is_active 欄位，但它繼承自 SoftModel
    if getattr(activity, 'is_deleted', False):
        raise OrderValidationError(f"活動 {activity.name} 已停用")
    
    # 檢查活動時間 - Activity 模型有 start_date 和 end_date
    if activity.start_date > now:
        raise OrderValidationError(f"活動 {activity.name} 尚未開始")
    
    if activity.end_date < now:
        raise OrderValidationError(f"活動 {activity.name} 已結束")
    
    # 檢查活動商品限制 - 需要通過 ActivityProduct 關聯檢查
    from ..models import ActivityProduct
    activity_product = ActivityProduct.objects.filter(
        activity=activity,
        product=product
    ).first()
    
    if not activity_product:
        raise OrderValidationError(f"商品 {product.product_name} 不在活動 {activity.name} 的適用範圍內")
    
    # ActivityProduct 模型沒有 max_quantity_per_order 欄位，可以跳過此檢查

def get_order_duplication_lock(user_id, cart_hash, timeout=30):
    """
    獲取訂單防重鎖
    
    參數:
        user_id: 用戶ID
        cart_hash: 購物車內容hash值
        timeout: 鎖定時間（秒）
    
    返回:
        lock_key: 鎖定鍵
        acquired: 是否成功獲取鎖
    """
    # 生成防重鎖key
    lock_key = f"order_duplication_lock:{user_id}:{cart_hash}"
    
    # 嘗試獲取鎖
    acquired = redis_client.set(lock_key, "1", nx=True, ex=timeout)
    
    return lock_key, acquired

def release_order_duplication_lock(lock_key):
    """釋放訂單防重鎖"""
    redis_client.delete(lock_key)

def calculate_cart_hash(cart_items):
    """
    計算購物車內容的hash值，用於防重檢查
    """
    cart_data = []
    for item in cart_items:
        cart_data.append(f"{item.product.id}:{item.quantity}")
    cart_data.sort()  # 排序以確保相同內容的hash值一致
    return hash("|".join(cart_data))

def check_inventory_availability(cart_items):
    """
    檢查庫存可用性
    不實際扣減庫存，只檢查是否足夠
    """
    for cart_item in cart_items:
        product = cart_item.product
        quantity = cart_item.quantity
        
        # 獲取產品對應的批號關聯 - ProductItemRelation 使用 'batch_components' 作為 related_name
        product_batch_relations = ProductItemRelation.objects.filter(
            product=product
        ).select_related('batch')
        
        if not product_batch_relations.exists():
            raise OrderValidationError(f"商品 {product.product_name} 沒有設定庫存關聯")
        
        for relation in product_batch_relations:
            batch = relation.batch
            if not batch:
                continue
            
            # 計算需要的庫存數量
            needed_quantity = int(relation.quantity * quantity)
            
            # 檢查批號庫存是否足夠 - Batch 模型有 available_stock 屬性
            if batch.available_stock < needed_quantity:
                raise OrderValidationError(f"商品 {product.product_name} 庫存不足")

def create_order_with_inventory_reservation(user, cart_items, shipping_info):
    """
    創建訂單並預留庫存，使用Redis鎖防止超賣
    增加了驗證和防重機制
    """
    # 計算購物車hash值
    cart_hash = calculate_cart_hash(cart_items)
    
    # 獲取防重鎖
    duplication_lock_key, duplication_lock_acquired = get_order_duplication_lock(user.id, cart_hash)
    
    if not duplication_lock_acquired:
        return None, "訂單正在處理中，請勿重複提交"
    
    try:
        # 驗證購物車商品
        validate_cart_items(cart_items)
        
        # 檢查庫存可用性
        check_inventory_availability(cart_items)
        
        # 獲取訂單配置
        config = OrderConfiguration.objects.first()
        if not config:
            config = OrderConfiguration.objects.create()  # 使用默認值
        
        # 生成訂單編號
        order_number = generate_order_number()
        
        # 計算付款截止時間
        payment_deadline = timezone.now() + timedelta(minutes=config.payment_timeout_minutes)
        
        # 批號庫存鎖相關變量
        batch_locks = {}
        batch_quantities = {}
        all_locks_acquired = True
        
        try:
            # 第一步：識別所有需要的批號和數量
            for cart_item in cart_items:
                product = cart_item.product
                quantity = cart_item.quantity
                
                # 獲取產品對應的批號關聯
                product_batch_relations = ProductItemRelation.objects.filter(
                    product=product
                ).select_related('batch', 'item')
                
                for relation in product_batch_relations:
                    batch = relation.batch
                    if not batch:
                        continue
                    
                    # 計算需要的庫存數量
                    needed_quantity = int(relation.quantity * quantity)
                    
                    # 累計批號需求量
                    if batch.id in batch_quantities:
                        batch_quantities[batch.id] += needed_quantity
                    else:
                        batch_quantities[batch.id] = needed_quantity
            
            # 第二步：嘗試為每個批號獲取Redis鎖
            for batch_id, needed_quantity in batch_quantities.items():
                # 創建鎖標識
                lock_key = f"batch_lock:{batch_id}"
                
                # 嘗試獲取鎖，有效期為配置的庫存鎖定時間
                acquired = redis_client.set(
                    lock_key, 
                    "1", 
                    nx=True, 
                    ex=config.inventory_lock_seconds
                )
                
                # 如果獲取鎖失敗，記錄並準備釋放所有已獲取的鎖
                if not acquired:
                    logger.warning(f"Failed to acquire lock for batch {batch_id}")
                    all_locks_acquired = False
                    break
                
                batch_locks[batch_id] = lock_key
                
            # 如果無法獲取所有鎖，釋放已獲取的鎖並返回失敗
            if not all_locks_acquired:
                for lock_key in batch_locks.values():
                    redis_client.delete(lock_key)
                return None, "庫存競爭，請稍後再試"
            
            # 第三步：在資料庫事務中創建訂單並預留庫存
            with transaction.atomic():
                # 再次檢查庫存（雙重檢查）
                check_inventory_availability(cart_items)
                
                # 創建訂單 - 使用正確的欄位名稱
                order = Order.objects.create(
                    user=user,
                    order_number=order_number,
                    status='pending_payment',
                    payment_deadline=payment_deadline,
                    lock_key=','.join(batch_locks.values()),
                    receiver_name=shipping_info.get('name', ''),
                    receiver_phone=shipping_info.get('phone', ''),
                    receiver_address=shipping_info.get('address', ''),
                    shipping_notes=shipping_info.get('notes', '')  # 如果有備註
                )
                
                # 創建訂單項目並計算金額
                total_amount = 0
                
                for cart_item in cart_items:
                    product = cart_item.product
                    quantity = cart_item.quantity
                    
                    # 從產品獲取價格 - 使用正確的關聯名稱
                    unit_price = 0
                    if hasattr(product, 'default_price'):
                        unit_price = product.default_price.price
                    
                    # 如果有活動，應用活動價格
                    if cart_item.activity:
                        # 從 ActivityProduct 獲取活動價格
                        from ..models import ActivityProduct
                        activity_product = ActivityProduct.objects.filter(
                            activity=cart_item.activity,
                            product=product
                        ).first()
                        
                        if activity_product:
                            unit_price = activity_product.price
                    
                    # 計算總價
                    item_total = unit_price * quantity
                    total_amount += item_total
                    
                    # 創建訂單項目
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        activity=cart_item.activity,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=item_total,
                        is_gift=False
                    )
                    
                    # 預留批號庫存
                    for relation in ProductItemRelation.objects.filter(product=product):
                        batch = relation.batch
                        if not batch:
                            continue
                        
                        # 計算需要的庫存數量
                        needed_quantity = int(relation.quantity * quantity)
                        
                        # 再次檢查批號庫存是否足夠
                        if batch.available_stock < needed_quantity:
                            # 庫存不足，回滾事務
                            raise OrderValidationError(f"商品 {product.product_name} (批號 {batch.batch_number}) 庫存不足")
                        
                        # 增加預留庫存
                        batch.reserved_stock += needed_quantity
                        batch.save()
                        
                        # 創建庫存預留記錄
                        reservation = InventoryReservation.objects.create(
                            order=order,
                            batch=batch,
                            item=relation.item,
                            quantity=needed_quantity,
                            is_confirmed=False,
                            expires_at=payment_deadline
                        )
                        
                        # 記錄操作日誌
                        OrderInventoryLog.objects.create(
                            order=order,
                            batch=batch,
                            operation='reserve',
                            quantity=needed_quantity,
                            note=f"為訂單 {order_number} 預留批號 {batch.batch_number} 庫存"
                        )
                
                # 更新訂單總金額
                order.total_amount = total_amount
                order.final_amount = total_amount  # 如有折扣可在此處理
                order.save()
                
                # 成功後釋放所有Redis鎖
                for lock_key in batch_locks.values():
                    redis_client.delete(lock_key)
                
                # 釋放防重鎖
                release_order_duplication_lock(duplication_lock_key)
                
                return order, None
                
        except Exception as e:
            # 發生異常，釋放所有Redis鎖
            for lock_key in batch_locks.values():
                redis_client.delete(lock_key)
            logger.exception(f"訂單創建失敗: {str(e)}")
            raise
            
    except OrderValidationError as e:
        # 驗證失敗
        release_order_duplication_lock(duplication_lock_key)
        logger.warning(f"訂單驗證失敗: {str(e)}")
        return None, str(e)
    except Exception as e:
        # 其他異常
        release_order_duplication_lock(duplication_lock_key)
        logger.exception(f"訂單創建失敗: {str(e)}")
        return None, str(e)

def confirm_order_payment(order_id, payment_info=None):
    """
    確認訂單付款，將預留庫存標記為確認
    """
    try:
        with transaction.atomic():
            # 獲取訂單
            order = Order.objects.select_for_update().get(id=order_id)
            
            # 檢查訂單狀態
            if order.status != 'pending_payment':
                return False, "訂單狀態不正確，無法確認付款"
            
            # 檢查付款截止時間
            if timezone.now() > order.payment_deadline:
                return False, "訂單已超過付款期限"
            
            # 更新訂單狀態
            order.status = 'paid'
            order.paid_at = timezone.now()
            if payment_info:
                order.payment_method = payment_info.get('method', '')
            order.save()
            
            # 確認所有庫存預留
            reservations = InventoryReservation.objects.filter(order=order)
            for reservation in reservations:
                # 標記預留為已確認
                reservation.is_confirmed = True
                reservation.save()
                
                # 記錄庫存日誌
                OrderInventoryLog.objects.create(
                    order=order,
                    batch=reservation.batch,
                    operation='confirm',
                    quantity=reservation.quantity,
                    note=f"確認訂單 {order.order_number} 付款，正式扣除批號 {reservation.batch.batch_number} 庫存"
                )
            
            return True, "訂單付款確認成功"
            
    except Order.DoesNotExist:
        return False, "訂單不存在"
    except Exception as e:
        logger.exception(f"確認訂單付款失敗: {str(e)}")
        return False, str(e)

def cancel_order(order_id, reason=None, user=None):
    """
    取消訂單並釋放庫存
    """
    try:
        with transaction.atomic():
            # 獲取訂單
            order = Order.objects.select_for_update().get(id=order_id)
            
            # 檢查訂單狀態
            if order.status not in ['pending_payment', 'paid']:
                return False, "訂單狀態不可取消"
            
            # 更新訂單狀態
            order.status = 'cancelled'
            order.cancelled_at = timezone.now()
            if reason:
                # Order 模型沒有 cancel_reason 欄位，可以放在 order_notes 中
                current_notes = order.order_notes or ""
                order.order_notes = f"{current_notes}\n取消原因: {reason}" if current_notes else f"取消原因: {reason}"
            order.save()
            
            # 釋放所有未確認的庫存預留
            reservations = InventoryReservation.objects.filter(
                order=order,
                is_confirmed=False
            )
            
            for reservation in reservations:
                batch = reservation.batch
                
                # 減少批號的預留庫存
                batch.reserved_stock -= reservation.quantity
                if batch.reserved_stock < 0:
                    batch.reserved_stock = 0
                batch.save()
                
                # 記錄庫存日誌
                OrderInventoryLog.objects.create(
                    order=order,
                    batch=batch,
                    operation='release',
                    quantity=reservation.quantity,
                    operator=user,
                    note=f"取消訂單 {order.order_number}，釋放批號 {batch.batch_number} 預留庫存。原因: {reason or '未指定'}"
                )
                
            # 如果訂單已付款，可能需要退款處理
            if order.status == 'paid':
                # TODO: 處理退款邏輯
                pass
                
            return True, "訂單取消成功"
            
    except Order.DoesNotExist:
        return False, "訂單不存在"
    except Exception as e:
        logger.exception(f"取消訂單失敗: {str(e)}")
        return False, str(e)

# 定期清理任務，可以使用Celery或Django管理命令
def cleanup_expired_reservations():
    """
    清理過期的庫存預留
    """
    now = timezone.now()
    expired_reservations = InventoryReservation.objects.filter(
        expires_at__lt=now,
        is_confirmed=False
    )
    
    for reservation in expired_reservations:
        batch = reservation.batch
        order = reservation.order
        
        # 減少批號的預留庫存
        batch.reserved_stock -= reservation.quantity
        if batch.reserved_stock < 0:
            batch.reserved_stock = 0
        batch.save()
        
        # 記錄庫存日誌
        OrderInventoryLog.objects.create(
            order=order,
            batch=batch,
            operation='expire',
            quantity=reservation.quantity,
            note=f"訂單 {order.order_number} 付款超時，自動釋放批號 {batch.batch_number} 預留庫存"
        )
        
        # 將訂單標記為已過期
        if order.status == 'pending_payment':
            order.status = 'expired'
            order.save()
    
    # 刪除過期預留記錄
    expired_reservations.delete()
    
    logger.info(f"清理了 {len(expired_reservations)} 條過期的庫存預留記錄")