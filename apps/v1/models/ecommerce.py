from django.db import models
from django.conf import settings
import django.utils.timezone as timezone
from utils.model import SoftModel, BaseModel
from simple_history.models import HistoricalRecords


class Product(SoftModel):
    """產品表（銷售、展示用）"""
    product_code = models.CharField("產品編號", max_length=50, unique=True)
    product_name = models.CharField("產品名稱", max_length=100)
    product_category = models.CharField("行銷類別", max_length=50, null=True, blank=True)
    is_promotion = models.BooleanField("促銷商品", default=False)
    can_be_gift = models.BooleanField("可作為贈品", default=False, help_text="標記此商品是否可以作為促銷活動的贈品")
    description = models.TextField("商品描述", null=True, blank=True)
    specification_html = models.TextField("規格HTML", null=True, blank=True)
    main_image_url = models.URLField("主圖URL", null=True, blank=True)
    tags = models.TextField("注意事項", null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "商品資料"
        verbose_name_plural = "商品資料"
        db_table = "v1_wms_product"
        ordering = ['product_code']

    def __str__(self):
        return f"{self.product_code} - {self.product_name}"


class ProductImage(BaseModel):
    """商品圖片表 - 不需要軟刪除，隨商品一起管理"""
    product = models.ForeignKey(Product, verbose_name="商品", on_delete=models.CASCADE, 
                               related_name="images")
    image_url = models.URLField("圖片URL")
    sort_order = models.IntegerField("排序", default=0)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "商品圖片"
        verbose_name_plural = "商品圖片"
        db_table = "v1_wms_product_image"
        ordering = ['product', 'sort_order']
    
    def __str__(self):
        return f"{self.product.product_name} - 圖片{self.sort_order}"


class ProductDefaultPrice(BaseModel):
    """商品常態價格表（非活動價格）"""
    product = models.OneToOneField(Product, verbose_name="商品", on_delete=models.CASCADE, related_name="default_price")
    price = models.DecimalField("售價", max_digits=10, decimal_places=2)
    stock = models.IntegerField("庫存數量", default=0)
    note = models.TextField("備註", null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "商品常態價格"
        verbose_name_plural = "商品常態價格"
        db_table = "v1_wms_product_default_price"

    def __str__(self):
        return f"{self.product.product_name} - NT${self.price}"


class Banner(SoftModel):
    """橫幅管理模型 - 適合軟刪除"""
    name = models.CharField("橫幅名稱", max_length=100)
    image_url = models.URLField("圖片URL")
    link_url = models.URLField("連結URL", null=True, blank=True)
    position = models.CharField("位置", max_length=50, default="home")
    start_date = models.DateTimeField("開始日期")
    end_date = models.DateTimeField("結束日期")
    description = models.TextField("描述", null=True, blank=True)
    is_active = models.BooleanField("是否啟用", default=True)
    priority = models.IntegerField("優先級", default=0)  # 數字越高優先級越高
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "橫幅管理"
        verbose_name_plural = "橫幅管理"
        db_table = "v1_wms_banner"
        ordering = ['-priority', '-start_date']
    
    def __str__(self):
        return self.name


class Cart(BaseModel):
    """購物車模型"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name="carts", verbose_name="用戶")
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "購物車"
        verbose_name_plural = "購物車"
        db_table = "v1_wms_cart"
    
    def __str__(self):
        return f"{self.user.username}的購物車"


class CartItem(BaseModel):
    """購物車項目模型"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items", 
                            verbose_name="購物車")
    product = models.ForeignKey('Product', on_delete=models.CASCADE, verbose_name="商品")
    activity = models.ForeignKey('v1.Activity', on_delete=models.SET_NULL, null=True, blank=True, 
                                verbose_name="活動")
    quantity = models.PositiveIntegerField("數量", default=1)
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "購物車項目"
        verbose_name_plural = "購物車項目"
        db_table = "v1_wms_cart_item"
        unique_together = ('cart', 'product', 'activity')
    
    def __str__(self):
        return f"{self.cart.user.username} - {self.product.product_name} x {self.quantity}"


class Order(SoftModel):
    """訂單主表"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="下單用戶", on_delete=models.SET_NULL, null=True)
    order_number = models.CharField("訂單編號", max_length=50, unique=True)
    
    # 修改狀態為您需要的流程
    STATUS_CHOICES = [
        ('pending_payment', '待付款'),  # 已預扣庫存，等待付款
        ('paid', '已付款'),            # 付款完成，已扣除庫存
        ('completed', '已完成'),        # 訂單已完成
        ('cancelled', '已取消'),        # 取消訂單，釋放庫存
        ('expired', '已逾期')          # 支付超時，釋放庫存
    ]
    status = models.CharField("狀態", max_length=20, choices=STATUS_CHOICES, default='pending_payment')
    
    # 保留原有欄位
    total_amount = models.DecimalField("總金額", max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField("折扣金額", max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField("實付金額", max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField("付款方式", max_length=20, null=True, blank=True)
    receiver_name = models.CharField("收件人姓名", max_length=50, null=True, blank=True)
    receiver_phone = models.CharField("聯絡電話", max_length=20, null=True, blank=True)
    receiver_address = models.TextField("收件地址", null=True, blank=True)
    shipping_notes = models.TextField("運輸備註", null=True, blank=True)
    order_notes = models.TextField("訂單備註", null=True, blank=True)
    
    # 新增時間追蹤欄位
    payment_deadline = models.DateTimeField("付款截止時間", null=True, blank=True)
    paid_at = models.DateTimeField("付款時間", null=True, blank=True)
    completed_at = models.DateTimeField("完成時間", null=True, blank=True)
    cancelled_at = models.DateTimeField("取消時間", null=True, blank=True)
    
    # Redis鎖相關
    lock_key = models.CharField("訂單鎖識別碼", max_length=100, null=True, blank=True)
    
    history = HistoricalRecords()

    class Meta:
        verbose_name = "訂單"
        verbose_name_plural = "訂單"
        db_table = "v1_wms_order"

    def __str__(self):
        return self.order_number


class OrderItem(BaseModel):
    """訂單明細"""
    order = models.ForeignKey(Order, verbose_name="訂單", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, verbose_name="產品", on_delete=models.SET_NULL, null=True)
    activity = models.ForeignKey('v1.Activity', verbose_name="所屬活動", on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField("數量")
    unit_price = models.DecimalField("單價", max_digits=10, decimal_places=2)
    total_price = models.DecimalField("總價", max_digits=10, decimal_places=2)
    is_gift = models.BooleanField("是否為贈品", default=False)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "訂單項目"
        verbose_name_plural = "訂單項目"
        db_table = "v1_wms_order_item"

    def __str__(self):
        return f"{self.order.order_number} - {self.product.product_name}"

class OrderConfiguration(BaseModel):
    """訂單流程設定"""
    payment_timeout_minutes = models.IntegerField("付款超時時間(分鐘)", default=30)
    inventory_lock_seconds = models.IntegerField("庫存鎖定時間(秒)", default=180)
    auto_cancel_enabled = models.BooleanField("啟用自動取消功能", default=True)
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "訂單設定"
        verbose_name_plural = "訂單設定"
        db_table = "v1_wms_order_configuration"
    
    def __str__(self):
        return f"訂單設定(付款超時:{self.payment_timeout_minutes}分鐘)"


class ShipmentItem(BaseModel):
    """出貨明細表 - 包含實際出貨的品號與批號資訊"""
    order_item = models.ForeignKey(OrderItem, verbose_name="訂單項目", on_delete=models.CASCADE, related_name="shipment_items")
    item_code = models.CharField("品號", max_length=50)
    batch_number = models.CharField("批號", max_length=50)
    quantity = models.IntegerField("出貨數量")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "出貨明細"
        verbose_name_plural = "出貨明細"
        db_table = "v1_wms_shipment_item"

    def __str__(self):
        return f"{self.item_code} ({self.batch_number}) x {self.quantity}"
    
class OrderInventoryLog(BaseModel):
    """訂單庫存操作日誌"""
    OPERATION_CHOICES = [
        ('reserve', '預留庫存'),
        ('confirm', '確認扣除'),
        ('release', '釋放庫存'),
    ]
    
    order = models.ForeignKey(Order, verbose_name="訂單", on_delete=models.CASCADE, 
                             related_name="inventory_logs")
    batch = models.ForeignKey('v1.Batch', verbose_name="批號", on_delete=models.CASCADE)
    operation = models.CharField("操作類型", max_length=20, choices=OPERATION_CHOICES)
    quantity = models.IntegerField("數量")
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="操作者", 
                                on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField("備註", null=True, blank=True)
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "訂單庫存日誌"
        verbose_name_plural = "訂單庫存日誌"
        db_table = "v1_wms_order_inventory_log"
        
    def __str__(self):
        return f"{self.order.order_number} - {self.get_operation_display()} {self.quantity}"