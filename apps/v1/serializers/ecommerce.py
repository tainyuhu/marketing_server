from rest_framework import serializers
from django.utils import timezone
from ..models.ecommerce import (
    OrderInventoryLog,
    Product,
    ProductImage,
    Banner,
    Cart,
    CartItem,
    Order,
    OrderItem,
    ShipmentItem
)
from ..models.promotion import Activity, ActivityProduct, PromotionRuleRelation
from django.db import models


class ProductImageSerializer(serializers.ModelSerializer):
    """商品圖片序列化器"""
    
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'sort_order', 'create_time']


class ProductListSerializer(serializers.ModelSerializer):
    """商品列表序列化器"""
    
    class Meta:
        model = Product
        fields = [
            'id', 'product_code', 'product_name', 'product_category',
            'is_promotion', 'main_image_url', 'tags',
            'create_time', 'update_time'
        ]


# class ProductDetailSerializer(serializers.ModelSerializer):
#     """商品詳情序列化器"""
#     images = ProductImageSerializer(many=True, read_only=True)
#     batch_components = serializers.SerializerMethodField()

#     class Meta:
#         model = Product
#         fields = '__all__'
    
#     def get_batch_components(self, obj):
#         from .warehouse import ProductItemRelationSerializer
#         components = obj.batch_components.all()
#         return ProductItemRelationSerializer(components, many=True).data

class ProductDetailSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    original_price = serializers.SerializerMethodField()
    is_promotion = serializers.SerializerMethodField()
    activity_name = serializers.SerializerMethodField()
    activity_id = serializers.SerializerMethodField()  # 添加活動ID字段
    has_stock = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)  # 商品圖片仍保留
    
    class Meta:
        model = Product
        fields = [
            'id', 'product_code', 'product_name', 'product_category',
            'description', 'specification_html', 'main_image_url',
            'tags', 'is_promotion', 'activity_name', 'activity_id',
            'price', 'original_price', 'has_stock', 'stock', 'images',
            'create_time', 'update_time'
        ]
    
    def get_price(self, obj):
        activity_product = obj.activities.filter(activity__end_date__gte=timezone.now()).first()
        if activity_product:
            return float(activity_product.price)
        return float(getattr(obj.default_price, "price", 0))
    
    def get_original_price(self, obj):
        activity_product = obj.activities.filter(activity__end_date__gte=timezone.now()).first()
        if activity_product:
            return float(activity_product.original_price)
        return float(getattr(obj.default_price, "price", 0))
    
    def get_is_promotion(self, obj):
        return obj.activities.filter(activity__end_date__gte=timezone.now()).exists()
    
    def get_activity_name(self, obj):
        activity_product = obj.activities.filter(activity__end_date__gte=timezone.now()).first()
        return activity_product.activity.name if activity_product else None
    
    def get_activity_id(self, obj):
        # 獲取活動ID
        activity_product = obj.activities.filter(activity__end_date__gte=timezone.now()).first()
        return activity_product.activity.id if activity_product else None
    
    def get_has_stock(self, obj):
        from apps.v1.models import ProductItemRelation
        relations = ProductItemRelation.objects.filter(product=obj).select_related("batch")
        total_stock = sum((r.batch.available_stock or 0) for r in relations if r.batch)
        return total_stock > 0
    
    def get_stock(self, obj):
        from apps.v1.models import ProductItemRelation
        relations = ProductItemRelation.objects.filter(product=obj).select_related("batch")
        return sum((r.batch.available_stock or 0) for r in relations if r.batch)



class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """商品建立/更新序列化器"""
    
    class Meta:
        model = Product
        fields = '__all__'
    
    def validate_product_code(self, value):
        """驗證產品編號唯一性"""
        instance = self.instance
        if Product.objects.filter(product_code=value).exists() and (instance is None or instance.product_code != value):
            raise serializers.ValidationError("產品編號已存在")
        return value


class BannerSerializer(serializers.ModelSerializer):
    """橫幅序列化器"""
    class Meta:
        model = Banner
        fields = [
            'id', 'name', 'image_url', 'link_url', 'position', 
            'start_date', 'end_date', 'description', 'is_active', 'priority'
        ]


class BannerResponseSerializer(serializers.ModelSerializer):
    """橫幅響應序列化器 - 前端格式"""
    imageUrl = serializers.URLField(source='image_url')
    
    class Meta:
        model = Banner
        fields = ['id', 'imageUrl', 'link_url']


class CartItemSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    imageUrl = serializers.SerializerMethodField()
    activityName = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    original_price = serializers.SerializerMethodField()
    gifts = serializers.SerializerMethodField()
    gift_quantity = serializers.SerializerMethodField()
    promotion_label = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'activity', 'quantity',
            'name', 'imageUrl', 'activityName',
            'price', 'original_price',
            'gifts', 'gift_quantity',
            'promotion_label'
        ]

    def get_name(self, obj):
        return obj.product.product_name if obj.product else "Unknown Product"

    def get_imageUrl(self, obj):
        return obj.product.main_image_url if obj.product else ""

    def get_activityName(self, obj):
        return obj.activity.name if obj.activity else ""

    def get_applicable_rule(self, obj):
        return PromotionRuleRelation.objects.filter(
            is_active=True
        ).filter(
            models.Q(product=obj.product) |
            models.Q(activity_product__product=obj.product, activity_product__activity=obj.activity) |
            models.Q(activity=obj.activity)
        ).order_by('-priority').first()

    def get_price(self, obj):
        rule_rel = self.get_applicable_rule(obj)
        
        # 如果有活動ID，嘗試獲取活動商品價格
        original_price = 0
        if obj.activity:
            try:
                # 從活動商品表中獲取價格
                activity_product = ActivityProduct.objects.filter(
                    activity=obj.activity,
                    product=obj.product
                ).first()
                if activity_product:
                    original_price = activity_product.price
            except Exception as e:
                print(f"Error getting activity price: {e}")
        
        # 如果沒有活動價格，嘗試獲取默認價格
        if original_price == 0 and hasattr(obj.product, 'default_price') and obj.product.default_price:
            try:
                original_price = obj.product.default_price.price
            except Exception:
                original_price = 0
        
        # 應用優惠規則
        if rule_rel and rule_rel.promotion_rule.rule_type == 'buy_discount':
            rule = rule_rel.promotion_rule
            if rule.threshold_quantity and obj.quantity >= rule.threshold_quantity:
                return float(original_price * (1 - rule.discount_rate))
        
        return float(original_price)

    def get_original_price(self, obj):
        if obj.activity:
            try:
                activity_product = ActivityProduct.objects.filter(
                    activity=obj.activity,
                    product=obj.product
                ).first()
                if activity_product:
                    return float(activity_product.original_price)
            except Exception:
                pass
        
        # 如果沒有活動原價，嘗試獲取默認價格
        try:
            if hasattr(obj.product, 'default_price') and obj.product.default_price:
                return float(obj.product.default_price.price)
            return 0
        except Exception:
            return 0

    def get_gift_quantity(self, obj):
        rule_rel = self.get_applicable_rule(obj)
        if rule_rel and rule_rel.promotion_rule.rule_type == 'buy_gift':
            rule = rule_rel.promotion_rule
            if rule.threshold_quantity and obj.quantity >= rule.threshold_quantity:
                return (obj.quantity // rule.threshold_quantity) * (rule.gift_quantity or 0)
        return 0

    def get_gifts(self, obj):
        rule_rel = self.get_applicable_rule(obj)
        rule = rule_rel.promotion_rule if rule_rel else None
        gift_product = rule.gift_product if rule and rule.rule_type == 'buy_gift' else None

        if gift_product and rule.threshold_quantity and obj.quantity >= rule.threshold_quantity:
            return [{
                "product_id": gift_product.id,
                "name": gift_product.product_name,
                "imageUrl": gift_product.main_image_url
            }]
        return []


    def get_promotion_label(self, obj):
        rule_rel = self.get_applicable_rule(obj)
        rule = rule_rel.promotion_rule if rule_rel else None
        if not rule:
            return ""
        if rule.rule_type == 'buy_discount' and rule.discount_rate:
            return f"{int(rule.discount_rate * 10)}折"
        elif rule.rule_type == 'buy_gift':
            return f"買{rule.threshold_quantity}送{rule.gift_quantity}"
        return ""


class CartItemCreateSerializer(serializers.Serializer):
    productId = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product'
    )
    quantity = serializers.IntegerField(min_value=1)
    activityId = serializers.PrimaryKeyRelatedField(
        queryset=Activity.objects.all(),
        source='activity',
        required=False,
        allow_null=True
    )

    def validate(self, data):
        product = data.get('product')
        activity = data.get('activity')

        # ✅ 活動有效性檢查
        if activity:
            now = timezone.now()
            if activity.start_date > now or activity.end_date < now:
                raise serializers.ValidationError("此活動尚未開始或已結束")
            
            # ✅ 活動是否包含此商品
            if not ActivityProduct.objects.filter(activity=activity, product=product).exists():
                raise serializers.ValidationError("該活動不包含此商品")

        return data

    def create(self, validated_data):
        user = self.context['request'].user
        cart, _ = Cart.objects.get_or_create(user=user)

        product = validated_data.get('product')
        activity = validated_data.get('activity')
        quantity = validated_data.get('quantity')

        # 檢查是否已存在該商品項目
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            activity=activity,
            defaults={'quantity': quantity}
        )

        # 若存在，直接加總數量
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        return cart_item


class OrderSerializer(serializers.ModelSerializer):
    """訂單序列化器"""
    
    class Meta:
        model = Order
        fields = '__all__'


class OrderItemSerializer(serializers.ModelSerializer):
    """訂單項目序列化器"""
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_code = serializers.CharField(source='product.product_code', read_only=True)
    activity_name = serializers.CharField(source='activity.name', read_only=True, allow_null=True)
    
    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'product', 'product_name', 'product_code', 
                 'activity', 'activity_name', 'quantity', 'unit_price', 
                 'total_price', 'is_gift']


class ShipmentItemSerializer(serializers.ModelSerializer):
    """出貨明細序列化器"""
    order_number = serializers.CharField(source='order_item.order.order_number', read_only=True)
    product_name = serializers.CharField(source='order_item.product.product_name', read_only=True)
    
    class Meta:
        model = ShipmentItem
        fields = ['id', 'order_item', 'order_number', 'product_name',
                 'item_code', 'batch_number', 'quantity']


# 統計報表相關序列化器
class ProductStockStatSerializer(serializers.Serializer):
    """商品庫存統計序列化器"""
    status = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()


class CategoryProductCountSerializer(serializers.Serializer):
    """類別商品數量統計序列化器"""
    category_name = serializers.CharField()
    product_count = serializers.IntegerField()
    percentage = serializers.FloatField()


class WarehouseStockSerializer(serializers.Serializer):
    """倉庫庫存統計序列化器"""
    warehouse = serializers.CharField()
    total_quantity = serializers.IntegerField()
    product_count = serializers.IntegerField()
    batch_count = serializers.IntegerField()


class ProductWithPricingSerializer(serializers.ModelSerializer):
    """商品帶價格序列化器"""
    price = serializers.SerializerMethodField()
    original_price = serializers.SerializerMethodField()
    is_promotion = serializers.SerializerMethodField()
    activity_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'product_name', 'main_image_url', 'price', 'original_price', 'is_promotion', 'activity_name']
    
    def get_price(self, obj):
        # 活動價格優先，否則回傳常態價格
        activity_product = obj.activities.filter(activity__end_date__gte=timezone.now()).first()
        if activity_product:
            return activity_product.price
        return getattr(obj.default_price, "price", 0)

    def get_original_price(self, obj):
        activity_product = obj.activities.filter(activity__end_date__gte=timezone.now()).first()
        if activity_product:
            return activity_product.original_price
        return getattr(obj.default_price, "price", 0)

    def get_is_promotion(self, obj):
        return obj.activities.filter(activity__end_date__gte=timezone.now()).exists()

    def get_activity_name(self, obj):
        activity_product = obj.activities.filter(activity__end_date__gte=timezone.now()).first()
        return activity_product.activity.name if activity_product else None
        
class OrderInventoryLogSerializer(serializers.ModelSerializer):
    batch_number = serializers.CharField(source='batch.batch_number', read_only=True)
    operation_display = serializers.CharField(source='get_operation_display', read_only=True)
    operator_name = serializers.CharField(source='operator.username', read_only=True, allow_null=True)
    
    class Meta:
        model = OrderInventoryLog
        fields = [
            'id', 'order', 'batch', 'batch_number', 'operation', 
            'operation_display', 'quantity', 'operator', 'operator_name',
            'note', 'create_time']