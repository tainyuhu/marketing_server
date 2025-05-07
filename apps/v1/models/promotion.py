from django.db import models
from django.conf import settings
import django.utils.timezone as timezone
from utils.model import SoftModel, BaseModel
from simple_history.models import HistoricalRecords
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


class Activity(SoftModel):
    """活動資料表 - 適合軟刪除，保留活動歷史記錄"""
    name = models.CharField("活動名稱", max_length=100)
    description = models.TextField("活動描述", null=True, blank=True)
    banner_url = models.URLField("橫幅圖片URL", null=True, blank=True)
    image_url = models.URLField("活動圖片URL", null=True, blank=True)
    start_date = models.DateTimeField("開始日期")
    end_date = models.DateTimeField("結束日期")
    detail_html = models.TextField("詳細內容HTML", null=True, blank=True)
    rules_html = models.TextField("規則HTML", null=True, blank=True)
    is_popular = models.BooleanField("熱門活動", default=False)
    progress = models.IntegerField("銷售進度", default=0)

    # 活動屬性
    activity_type = models.CharField(
        "活動類型",
        max_length=30,
        choices=[
            ('sitewide_discount', '全館折扣'),
            ('product_promotion', '商品促銷'),
            ('internal_promotion', '內建單品優惠'),
        ],
        default='product_promotion'
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "促銷活動"
        verbose_name_plural = "促銷活動"
        db_table = "v1_wms_activity"
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    @property
    def remaining_days(self):
        today = timezone.now().date()
        delta = self.end_date.date() - today
        return max(0, delta.days)


class ActivityProduct(BaseModel):
    """活動商品關聯表 - 支援各種優惠形式"""
    activity = models.ForeignKey(Activity, verbose_name="活動", on_delete=models.CASCADE, related_name="products")
    product = models.ForeignKey('v1.Product', verbose_name="商品", on_delete=models.CASCADE, related_name="activities")
    price = models.DecimalField("活動價格", max_digits=10, decimal_places=2)
    original_price = models.DecimalField("原價", max_digits=10, decimal_places=2)
    special_tag = models.CharField("特殊標籤", max_length=50, null=True, blank=True)
    stock = models.IntegerField("活動庫存", default=0)
    note = models.TextField("備註", null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "活動商品"
        verbose_name_plural = "活動商品"
        db_table = "v1_wms_activity_product"
        ordering = ['activity', 'id']
        unique_together = ('activity', 'product')

    def __str__(self):
        return f"{self.activity.name} - {self.product.product_name}"
    
    def calculate_available_stock(self):
        """
        Calculate available stock based on the product's component batches.
        Returns the maximum number of products that can be produced.
        """
        # Import here to avoid circular imports
        from .warehouse import ProductItemRelation
        
        # Get the product for this activity product
        product = self.product
        
        # Get all related item relations for this product
        item_relations = ProductItemRelation.objects.filter(product=product)
        
        if not item_relations.exists():
            # If no components are defined, return 0 or some default value
            return 0
        
        # Calculate how many products can be produced based on each component
        max_products_per_component = []
        
        for relation in item_relations:
            # For each component, check how many products can be made
            if relation.quantity <= 0:
                # If quantity required is 0 or negative, this doesn't limit production
                continue
                
            batch = relation.batch
            if not batch:
                # If no specific batch is assigned, return 0 or handle differently
                return 0
                
            # Calculate how many products can be made from this batch
            if batch.quantity > 0:
                max_products = batch.quantity // relation.quantity
                max_products_per_component.append(max_products)
        
        # The available stock is limited by the component with the lowest availability
        if max_products_per_component:
            return min(max_products_per_component)
        return 0
    
    def update_stock(self):
        """Update the stock field based on calculated availability"""
        calculated_stock = self.calculate_available_stock()
        
        # Only update if different to avoid unnecessary database operations
        if self.stock != calculated_stock:
            self.stock = calculated_stock
            # Use update to avoid triggering post_save again
            ActivityProduct.objects.filter(id=self.id).update(stock=calculated_stock)
            
    def save(self, *args, **kwargs):
        """Override save to update stock before saving"""
        # For new records, save first to get an ID
        if not self.id:
            super().save(*args, **kwargs)
            self.update_stock()
        else:
            self.update_stock()
            super().save(*args, **kwargs)


class PromotionRule(BaseModel):
    """促銷規則，用於管理不同優惠條件的組合與邏輯"""
    name = models.CharField("規則名稱", max_length=100)
    description = models.TextField("描述", null=True, blank=True)
    rule_type = models.CharField("規則類型", max_length=50, choices=[
        ('buy_gift', '買贈'),
        ('buy_discount', '買折扣'),
        ('order_discount', '滿額折'),
        ('order_free_shipping', '免運'),
    ])
    threshold_amount = models.DecimalField("門檻金額", max_digits=10, decimal_places=2, null=True, blank=True)
    threshold_quantity = models.IntegerField("門檻數量", null=True, blank=True)
    discount_rate = models.DecimalField("折扣比例", max_digits=4, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField("折扣金額", max_digits=10, decimal_places=2, null=True, blank=True)
    is_stackable = models.BooleanField("是否可疊加", default=False)
    limit_per_user = models.IntegerField("每人限制次數", null=True, blank=True)
    is_gift_same_product = models.BooleanField("是否為贈品同商品", default=False)
    gift_product = models.ForeignKey('v1.Product', verbose_name="贈送商品", 
                                    on_delete=models.SET_NULL, null=True, blank=True, 
                                    related_name="promotion_gifts",
                                    help_text="買贈活動中贈送的商品")
    gift_quantity = models.IntegerField("贈送數量", default=1, null=True, blank=True,
                                      help_text="買贈活動中贈送的商品數量")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "促銷規則"
        verbose_name_plural = "促銷規則"
        db_table = "v1_wms_promotion_rule"

    def __str__(self):
        return self.name


class PromotionRuleRelation(BaseModel):
    """
    促銷規則關聯表 - 將促銷規則與活動、商品或活動商品關聯
    三種關聯類型互斥，只能存在一種:
    
    1. 若為 is_sitewide=True，則不應綁定任何對象（活動/商品/活動商品皆為 NULL）
    2. 若為 activity=xxx：表示整個活動期間套用此促銷邏輯
    3. 若為 product=xxx：表示該商品無論是否在活動中皆可套用促銷
    4. 若為 activity_product=xxx：表示僅該活動商品可享此優惠
    """
    promotion_rule = models.ForeignKey(PromotionRule, on_delete=models.CASCADE, 
                                      related_name='relations', verbose_name="促銷規則")
    
    # 三種可能的關聯對象，互斥存在
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE,
                                null=True, blank=True, related_name='promotion_rules',
                                verbose_name="關聯活動")
    
    product = models.ForeignKey('v1.Product', on_delete=models.CASCADE,
                               null=True, blank=True, related_name='promotion_rules',
                               verbose_name="關聯商品")
    
    activity_product = models.ForeignKey(ActivityProduct, on_delete=models.CASCADE,
                                       null=True, blank=True, related_name='promotion_rules',
                                       verbose_name="關聯活動商品")
    
    is_sitewide = models.BooleanField("是否適用全商城", default=False)
    is_active = models.BooleanField("是否啟用", default=True)
    priority = models.IntegerField("優先級", default=0, help_text="數字越高優先級越高，用於多重規則排序")
    
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "促銷規則關聯"
        verbose_name_plural = "促銷規則關聯"
        db_table = "v1_wms_promotion_rule_relation"
        ordering = ['-priority', 'id']  # 確保排序的穩定性
        
    
    def clean(self):
        """確保三種關聯類型互斥存在"""
        relation_count = sum(1 for field in [self.activity, self.product, self.activity_product] if field is not None)
        
        # 如果是全商城規則，則不應該有特定關聯
        if self.is_sitewide and relation_count > 0:
            raise ValidationError("全商城規則不應關聯特定活動或商品")
            
        # 如果不是全商城規則，則必須關聯到其中一種對象
        if not self.is_sitewide and relation_count != 1:
            raise ValidationError("必須且只能關聯到活動、商品或活動商品其中之一")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.is_sitewide:
            return f"{self.promotion_rule.name} (全商城規則) [優先級: {self.priority}]"
        elif self.activity:
            return f"{self.promotion_rule.name} - 活動: {self.activity.name} [優先級: {self.priority}]"
        elif self.product:
            return f"{self.promotion_rule.name} - 商品: {self.product.product_name} [優先級: {self.priority}]"
        elif self.activity_product:
            product_name = self.activity_product.product.product_name
            activity_name = self.activity_product.activity.name
            return f"{self.promotion_rule.name} - 活動商品: {product_name} ({activity_name}) [優先級: {self.priority}]"
        return f"{self.promotion_rule.name} - 未知關聯 [優先級: {self.priority}]"


class UserActivityLog(BaseModel):
    """使用者活動參與紀錄（是否參與活動、有無領取贈品）"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="使用者", on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, verbose_name="活動", on_delete=models.CASCADE)
    joined_at = models.DateTimeField("參與時間", auto_now_add=True)
    received_gift = models.BooleanField("已領取贈品", default=False)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "使用者活動紀錄"
        verbose_name_plural = "使用者活動紀錄"
        db_table = "v1_wms_user_activity_log"
        unique_together = ('user', 'activity')

    def __str__(self):
        return f"{self.user} - {self.activity.name}"