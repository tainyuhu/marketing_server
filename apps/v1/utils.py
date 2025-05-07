# utils.py

def recalculate_all_activity_product_stock():
    """
    Utility function to recalculate stock for all ActivityProduct records.
    This can be called from a management command, admin action, or after imports.
    """
    from .models import ActivityProduct
    
    activity_products = ActivityProduct.objects.all()
    updated_count = 0
    
    for ap in activity_products:
        old_stock = ap.stock
        new_stock = ap.calculate_available_stock()
        
        if old_stock != new_stock:
            # Use update to avoid triggering signals
            ActivityProduct.objects.filter(id=ap.id).update(stock=new_stock)
            updated_count += 1
    
    return updated_count


import uuid
import redis
import logging
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.conf import settings
from .models import (
    Order, OrderItem, Batch, InventoryReservation, 
    OrderInventoryLog, OrderConfiguration, ProductItemRelation
)

logger = logging.getLogger(__name__)

# 創建Redis連接
redis_client = redis.Redis.from_url(settings.REDIS_URL)

def create_order_with_inventory_reservation(user, cart_items, shipping_info):
    """
    創建訂單並預留庫存，使用Redis鎖防止超賣
    """
    # 獲取訂單配置
    config = OrderConfiguration.objects.first()
    if not config:
        config = OrderConfiguration.objects.create()  # 使用默認值
    
    # 生成訂單編號
    order_number = f"ORD-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    
    # 計算付款截止時間
    payment_deadline = timezone.now() + timedelta(minutes=config.payment_timeout_minutes)
    
    # 嘗試獲取所有需要的批號的庫存鎖
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
        
        # 第三步：檢查庫存是否足夠，並在資料庫事務中預留庫存
        with transaction.atomic():
            # 先創建訂單
            order = Order.objects.create(
                user=user,
                order_number=order_number,
                status='pending_payment',
                payment_deadline=payment_deadline,
                lock_key=','.join(batch_locks.values()),
                receiver_name=shipping_info.get('name', ''),
                receiver_phone=shipping_info.get('phone', ''),
                receiver_address=shipping_info.get('address', '')
            )
            
            # 創建訂單項目並計算金額
            total_amount = 0
            
            for cart_item in cart_items:
                product = cart_item.product
                quantity = cart_item.quantity
                
                # 從產品獲取價格
                if hasattr(product, 'default_price'):
                    unit_price = product.default_price.price
                else:
                    unit_price = 0
                
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
                    
                    # 檢查批號庫存是否足夠
                    if batch.available_stock < needed_quantity:
                        # 庫存不足，回滾事務
                        raise Exception(f"批號 {batch.batch_number} 庫存不足")
                    
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
            
            return order, None
            
    except Exception as e:
        # 發生異常，釋放所有Redis鎖
        for lock_key in batch_locks.values():
            redis_client.delete(lock_key)
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
                
            return True, "訂單取消成功"
            
    except Order.DoesNotExist:
        return False, "訂單不存在"
    except Exception as e:
        logger.exception(f"取消訂單失敗: {str(e)}")
        return False, str(e)
    
