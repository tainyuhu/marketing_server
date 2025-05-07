from django.db import models
from django.conf import settings
import django.utils.timezone as timezone
from utils.model import SoftModel, BaseModel
from simple_history.models import HistoricalRecords


class MaterialCategory(SoftModel):
    """物料類別資料表"""
    name = models.CharField("類別名稱", max_length=50)
    description = models.TextField("類別描述", null=True, blank=True)
    item_count = models.IntegerField("品號數量", default=0)
    parent = models.ForeignKey('self', verbose_name="父類別", on_delete=models.CASCADE, 
                               null=True, blank=True, related_name="children")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "物料類別"
        verbose_name_plural = "物料類別"
        db_table = "v1_wms_material_category"
        ordering = ['id']

    def __str__(self):
        return self.name


class Item(BaseModel):
    """品號表（單一物料單位）"""
    item_code = models.CharField("品號代碼", max_length=50, unique=True)
    name = models.CharField("品名", max_length=100)
    material_category = models.ForeignKey('MaterialCategory', verbose_name="物料類別", 
                                    on_delete=models.SET_NULL, null=True, blank=True, 
                                    related_name="items")
    specification = models.CharField("規格", max_length=100, null=True, blank=True)
    unit = models.CharField("單位", max_length=20, default='pcs')
    box_size = models.IntegerField("箱入數", default=0)
    status = models.BooleanField("啟用狀態", default=True)
    remark = models.TextField("備註", null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'v1_wms_item'
        verbose_name = "品號"
        verbose_name_plural = "品號"

    def __str__(self):
        return f"{self.item_code} - {self.name}"


class Category(SoftModel):
    """商品類別資料表"""
    name = models.CharField("類別名稱", max_length=50)
    description = models.TextField("類別描述", null=True, blank=True)
    product_count = models.IntegerField("產品數量", default=0)
    parent = models.ForeignKey('self', verbose_name="父類別", on_delete=models.CASCADE, 
                               null=True, blank=True, related_name="children")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "商品類別"
        verbose_name_plural = "商品類別"
        db_table = "v1_wms_category"
        ordering = ['id']

    def __str__(self):
        return self.name


class Batch(SoftModel):
    """批號表（每批品號的實際庫存與效期）"""
    item = models.ForeignKey('Item', on_delete=models.CASCADE, related_name="batches", null=True, blank=True)
    batch_number = models.CharField("批號", max_length=50, unique=True)
    warehouse = models.CharField("倉庫", max_length=50)
    location = models.CharField("儲位", max_length=50, null=True, blank=True)

    quantity = models.IntegerField("總數量", default=0)
    active_stock = models.IntegerField("活動庫存", default=0)
    stock = models.IntegerField("常態庫存", default=0)
    # 新增預留庫存欄位
    reserved_stock = models.IntegerField("預留庫存", default=0)
    box_count = models.IntegerField("箱數", default=0)

    expiry_date = models.DateField("效期", null=True, blank=True)
    days_to_expiry = models.IntegerField("剩餘天數", null=True, blank=True)

    state = models.CharField(
        "狀態", max_length=20,
        choices=[('active', '正常'), ('locked', '鎖定'), ('quarantine', '隔離'), ('expired', '過期')],
        default='active'
    )
    history = HistoricalRecords()

    class Meta:
        db_table = 'v1_wms_batch'
        verbose_name = "批號"
        verbose_name_plural = "批號"
        ordering = ['expiry_date', 'batch_number']

    def __str__(self):
        return f"{self.item.item_code} - {self.batch_number}"
    
    def save(self, *args, **kwargs):
        if self.expiry_date:
            today = timezone.now().date()
            delta = self.expiry_date - today
            self.days_to_expiry = delta.days
            if self.days_to_expiry <= 0:
                self.state = 'expired'

        # 修改庫存計算邏輯，包含預留庫存
        if self.active_stock + self.stock + self.reserved_stock != self.quantity:
            self.stock = self.quantity - self.active_stock - self.reserved_stock

        super().save(*args, **kwargs)

    @property
    def available_stock(self):
        """實際可用庫存（常態 + 活動 - 預留）"""
        return (self.stock or 0) + (self.active_stock or 0) - (self.reserved_stock or 0)

class InventoryReservation(BaseModel):
    """庫存預留記錄"""
    order = models.ForeignKey('v1.Order', verbose_name="訂單", on_delete=models.CASCADE, 
                             related_name="inventory_reservations")
    batch = models.ForeignKey('Batch', verbose_name="批號", on_delete=models.CASCADE,
                             related_name="reservations")
    item = models.ForeignKey('Item', verbose_name="品號", on_delete=models.CASCADE)
    quantity = models.IntegerField("預留數量")
    is_confirmed = models.BooleanField("是否確認", default=False)
    expires_at = models.DateTimeField("預留過期時間", null=True)
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "庫存預留"
        verbose_name_plural = "庫存預留"
        db_table = "v1_wms_inventory_reservation"
        
    def __str__(self):
        return f"訂單 {self.order.order_number} - {self.batch.batch_number} x {self.quantity}"


class ProductItemRelation(BaseModel):
    """產品對應使用哪些品號、批號與數量（精確控管）"""
    product = models.ForeignKey('v1.Product', on_delete=models.CASCADE, related_name='batch_components')
    item = models.ForeignKey('Item', on_delete=models.CASCADE, related_name='used_in_product_batches')
    batch = models.ForeignKey('Batch', on_delete=models.SET_NULL, null=True, blank=True, related_name='product_relations')
    quantity = models.FloatField("用量", default=1)
    unit = models.CharField("單位", max_length=20, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'v1_wms_product_item_relation'
        unique_together = ('product', 'batch')
        verbose_name = "產品-品號批號關聯"
        verbose_name_plural = "產品-品號批號關聯"

    def __str__(self):
        product_code = self.product.product_code if self.product else "?"
        batch_number = self.batch.batch_number if self.batch else "?"
        return f"{product_code} → {batch_number} x {self.quantity}"


# Signal handlers to update stock calculations
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=Batch)
def update_product_stock_on_batch_change(sender, instance, **kwargs):
    """
    When a batch is updated, update the stock for all activity products
    that use this batch through product item relations.
    """
    # Import here to avoid circular imports
    from .promotion import ActivityProduct
    
    # Find all products using this batch
    relations = ProductItemRelation.objects.filter(batch=instance)
    
    # Get unique products
    affected_products = set(relation.product for relation in relations)
    
    # Update all activity products for these products
    for product in affected_products:
        activity_products = ActivityProduct.objects.filter(product=product)
        for ap in activity_products:
            ap.update_stock()

@receiver(post_save, sender=ProductItemRelation)
@receiver(post_delete, sender=ProductItemRelation)
def update_product_stock_on_relation_change(sender, instance, **kwargs):
    """
    When a product-item relation is changed or deleted,
    update the stock for all related activity products.
    """
    # Import here to avoid circular imports
    from .promotion import ActivityProduct
    
    # Get the affected product
    product = instance.product
    
    # Update all activity products for this product
    activity_products = ActivityProduct.objects.filter(product=product)
    for ap in activity_products:
        ap.update_stock()


