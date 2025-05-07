from rest_framework import serializers
from ..models.warehouse import (
    InventoryReservation,
    MaterialCategory, 
    Item, 
    Category, 
    Batch, 
    ProductItemRelation
)


class MaterialCategorySerializer(serializers.ModelSerializer):
    """物料類別序列化器"""
    class Meta:
        model = MaterialCategory
        fields = '__all__'


class MaterialCategoryTreeSerializer(serializers.ModelSerializer):
    """物料類別樹狀結構序列化器"""
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = MaterialCategory
        fields = ['id', 'name', 'description', 'item_count', 'children']
    
    def get_children(self, obj):
        children = MaterialCategory.objects.filter(parent=obj)
        serializer = MaterialCategoryTreeSerializer(children, many=True)
        return serializer.data


class MaterialCategoryItemCountSerializer(serializers.Serializer):
    """物料類別品項數量統計序列化器"""
    category_name = serializers.CharField()
    item_count = serializers.IntegerField()
    percentage = serializers.FloatField()


class CategorySerializer(serializers.ModelSerializer):
    """類別序列化器"""
    
    class Meta:
        model = Category
        fields = '__all__'


class CategoryTreeSerializer(serializers.ModelSerializer):
    """包含子類別的樹狀結構序列化器"""
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'product_count', 'create_time', 'update_time', 'children']
    
    def get_children(self, obj):
        """獲取子類別並遞歸序列化"""
        children = Category.objects.filter(parent=obj)
        serializer = CategoryTreeSerializer(children, many=True)
        return serializer.data


class ItemSerializer(serializers.ModelSerializer):
    """品號序列化器"""
    material_category_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Item
        fields = '__all__'
    
    def get_material_category_name(self, obj):
        if obj.material_category:
            return obj.material_category.name
        return None


class ItemCreateUpdateSerializer(serializers.ModelSerializer):
    """品號創建和更新序列化器"""
    class Meta:
        model = Item
        fields = ['item_code', 'name', 'material_category', 'specification', 
                 'unit', 'box_size', 'status', 'remark']


class ProductItemRelationSerializer(serializers.ModelSerializer):
    """產品品項關係序列化器"""
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    batch_number = serializers.CharField(source='batch.batch_number', read_only=True)
    warehouse = serializers.CharField(source='batch.warehouse', read_only=True)
    expiry_date = serializers.DateField(source='batch.expiry_date', read_only=True)

    class Meta:
        model = ProductItemRelation
        fields = ['id', 'product', 'item', 'batch', 'item_code', 'item_name', 'batch_number', 'warehouse', 'expiry_date', 'quantity', 'unit']


class BatchListSerializer(serializers.ModelSerializer):
    """批號列表序列化器"""
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    available_stock = serializers.IntegerField(source='available_stock', read_only=True)
    
    class Meta:
        model = Batch
        fields = [
            'id', 'item', 'item_code', 'item_name', 'batch_number', 'warehouse', 'location',
            'state', 'quantity', 'active_stock', 'stock', 'box_count', 'available_stock',
            'expiry_date', 'days_to_expiry',
            'create_time', 'update_time'
        ]


class BatchDetailSerializer(serializers.ModelSerializer):
    """批號詳情序列化器"""
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    
    class Meta:
        model = Batch
        fields = '__all__'


class BatchCreateUpdateSerializer(serializers.ModelSerializer):
    """批號建立/更新序列化器"""
    
    class Meta:
        model = Batch
        exclude = ['days_to_expiry']
    
    def validate_batch_number(self, value):
        """驗證批號唯一性"""
        instance = self.instance
        if Batch.objects.filter(batch_number=value).exists() and (instance is None or instance.batch_number != value):
            raise serializers.ValidationError("批號已存在")
        return value
    
    def validate(self, data):
        """驗證數量關係"""
        quantity = data.get('quantity', 0)
        active_stock = data.get('active_stock', 0)
        
        if active_stock > quantity:
            raise serializers.ValidationError({
                "active_stock": "活動庫存不能大於總數量"
            })
        
        return data

class InventoryReservationSerializer(serializers.ModelSerializer):
    batch_number = serializers.CharField(source='batch.batch_number', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    
    class Meta:
        model = InventoryReservation
        fields = [
            'id', 'order', 'batch', 'batch_number', 'item', 'item_code', 
            'item_name', 'quantity', 'is_confirmed', 'expires_at', 
            'create_time', 'update_time'
        ]