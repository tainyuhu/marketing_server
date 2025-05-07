from rest_framework import serializers
from ..models.promotion import (
    Activity,
    ActivityProduct,
    PromotionRule,
    PromotionRuleRelation,
    UserActivityLog,
)

from ..models.ecommerce import Product

class GiftProductBriefSerializer(serializers.ModelSerializer):
    """贈品簡要資料序列化"""
    class Meta:
        model = Product  # 確認是你自己的 Product 模型
        fields = ['id', 'product_code', 'product_name', 'main_image_url']


class ActivityProductSerializer(serializers.ModelSerializer):
    """活動商品序列化器"""
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_code = serializers.CharField(source='product.product_code', read_only=True)
    main_image_url = serializers.URLField(source='product.main_image_url', read_only=True)
    promotion_rules = serializers.SerializerMethodField()

    # 新增贈品明細欄位
    gift_product_detail = GiftProductBriefSerializer(source='promotion_rules.first.promotion_rule.gift_product', read_only=True)
    
    class Meta:
        model = ActivityProduct
        fields = [
            'id', 'product', 'product_name', 'product_code',
            'price', 'original_price', 'special_tag', 'stock',
            'main_image_url',
            'note',
            'promotion_rules',
            # 贈品邏輯欄位
            'gift_product_detail',  # ← 新增這個欄位！
        ]
    
    def get_promotion_rules(self, obj):
        rule_relations = obj.promotion_rules.filter(is_active=True)
        return PromotionRuleSerializer([r.promotion_rule for r in rule_relations], many=True).data



class ActivityListSerializer(serializers.ModelSerializer):
    """活動列表序列化器"""
    remaining_days = serializers.IntegerField(read_only=True)
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Activity
        fields = '__all__'
    
    def get_product_count(self, obj):
        """獲取活動商品數量"""
        return obj.products.count()


class ActivityDetailSerializer(serializers.ModelSerializer):
    """活動詳情序列化器"""
    products = ActivityProductSerializer(source='products.all', many=True, read_only=True)
    remaining_days = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Activity
        fields = '__all__'


class ActivityProductCreateUpdateSerializer(serializers.ModelSerializer):
    """活動商品關聯建立/更新序列化器"""
    
    class Meta:
        model = ActivityProduct
        fields = '__all__'
    
    def validate(self, data):
        """驗證價格關係"""
        price = data.get('price', 0)
        original_price = data.get('original_price', 0)
        
        if price > original_price:
            raise serializers.ValidationError({
                "price": "活動價格不能大於原價"
            })
        
        # 檢查是否已經存在相同的活動商品關聯
        activity = data.get('activity')
        product = data.get('product')
        instance = self.instance
        
        if ActivityProduct.objects.filter(activity=activity, product=product).exists() and (
            instance is None or instance.activity != activity or instance.product != product
        ):
            raise serializers.ValidationError("該商品已添加到此活動中")
        
        return data


class HotSaleActivitySerializer(serializers.ModelSerializer):
    """熱銷活動序列化器 - 前端格式"""
    bannerUrl = serializers.URLField(source='banner_url')
    endDate = serializers.DateTimeField(source='end_date')
    products = serializers.SerializerMethodField('get_hot_sale_products')

    class Meta:
        model = Activity
        fields = ['id', 'name', 'bannerUrl', 'endDate', 'products']

    def get_hot_sale_products(self, obj):
        """獲取熱銷活動的商品（最多前 8 筆）"""
        activity_products = ActivityProduct.objects.filter(
            activity=obj
        ).select_related('product')[:8]

        return [{
            'id': str(ap.product.id),
            'name': ap.product.product_name,
            'shortDescription': (ap.product.description or "")[:100],
            'price': float(ap.price),
            'originalPrice': float(ap.original_price) if ap.original_price else None,
            'imageUrl': ap.product.main_image_url,
            'specialTag': ap.special_tag,
        } for ap in activity_products]


class PromotionRuleSerializer(serializers.ModelSerializer):
    """促銷規則序列化器"""
    rule_type_display = serializers.CharField(source='get_rule_type_display', read_only=True)
    
    class Meta:
        model = PromotionRule
        fields = '__all__'


class PromotionRuleRelationSerializer(serializers.ModelSerializer):
    """促銷規則關聯序列化器"""
    promotion_rule_name = serializers.CharField(source='promotion_rule.name', read_only=True)
    rule_type = serializers.CharField(source='promotion_rule.rule_type', read_only=True)
    rule_type_display = serializers.CharField(source='promotion_rule.get_rule_type_display', read_only=True)
    related_object_name = serializers.SerializerMethodField()
    
    class Meta:
        model = PromotionRuleRelation
        fields = '__all__'
    
    def get_related_object_name(self, obj):
        """獲取關聯對象名稱"""
        if obj.is_sitewide:
            return "全商城優惠"
        elif obj.activity:
            return f"活動: {obj.activity.name}"
        elif obj.product:
            return f"商品: {obj.product.product_name}"
        elif obj.activity_product:
            return f"活動商品: {obj.activity_product.product.product_name} ({obj.activity_product.activity.name})"
        return "未知關聯"


class UserActivityLogSerializer(serializers.ModelSerializer):
    """使用者活動參與紀錄序列化器"""
    user_name = serializers.CharField(source='user.username', read_only=True)
    activity_name = serializers.CharField(source='activity.name', read_only=True)
    
    class Meta:
        model = UserActivityLog
        fields = ['id', 'user', 'user_name', 'activity', 'activity_name', 
                 'joined_at', 'received_gift']


class HistoricalRecordSerializer(serializers.Serializer):
    """歷史記錄序列化器"""
    id = serializers.IntegerField()
    history_id = serializers.UUIDField()
    history_date = serializers.DateTimeField()
    history_type = serializers.CharField()
    history_type_display = serializers.SerializerMethodField()
    history_user = serializers.PrimaryKeyRelatedField(read_only=True)
    history_user_name = serializers.SerializerMethodField()
    history_change_reason = serializers.CharField(allow_null=True, required=False)
    changes = serializers.SerializerMethodField()

    def get_history_user_name(self, obj):
        return obj.history_user.username if obj.history_user else None

    def get_history_type_display(self, obj):
        return {
            '+': '新增',
            '~': '修改',
            '-': '刪除'
        }.get(obj.history_type, obj.history_type)
    
    def get_changes(self, obj):
        try:
            # diff_against 需依賴 simple_history 的擴展方法
            diff = obj.diff_against(obj.prev_record)
            return {
                change.field: {
                    "from": str(change.old),
                    "to": str(change.new)
                }
                for change in diff.changes
            }
        except Exception as e:
            # 若無法比較（如第一筆、已刪除對象），回傳空字典
            return {}