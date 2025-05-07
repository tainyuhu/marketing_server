# tasks.py
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from .models import Order, InventoryReservation, OrderInventoryLog, Batch

@shared_task
def check_expired_orders():
    """
    檢查並處理過期的訂單
    """
    process_expired_orders()

def process_expired_orders():
    """
    處理已過支付期限的訂單
    1. 找出已過支付期限的「待付款」訂單
    2. 將其狀態更新為「已逾期」
    3. 釋放其預留的庫存
    """
    # 找出已過付款期限的訂單
    now = timezone.now()
    expired_orders = Order.objects.filter(
        status='pending_payment',
        payment_deadline__lt=now
    )
    
    for order in expired_orders:
        with transaction.atomic():
            # 更新訂單狀態為逾期
            order.status = 'expired'
            order.save()
            
            # 釋放所有預留庫存
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
                    note=f"訂單 {order.order_number} 付款逾期，自動釋放批號 {batch.batch_number} 預留庫存"
                )