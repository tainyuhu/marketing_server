from rest_framework import status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum

from utils.view import TrackedAPIView
from ..models import (
    Item, Category, MaterialCategory, Product, ProductImage, ProductItemRelation, Batch
)
from ..serializers import (
    HistoricalRecordSerializer, ItemCreateUpdateSerializer, ItemSerializer, 
    CategorySerializer, CategoryTreeSerializer, MaterialCategoryItemCountSerializer, 
    MaterialCategorySerializer, MaterialCategoryTreeSerializer, 
    ProductListSerializer, ProductItemRelationSerializer,
    BatchListSerializer, BatchDetailSerializer, BatchCreateUpdateSerializer,
    WarehouseStockSerializer
)
from ..filters import (
    ItemFilter, MaterialCategoryFilter, BatchFilter
)


class ModelHistoryViewMixin:
    """為模型添加歷史查看能力的混入類"""
    @action(detail=True, methods=['get'], url_name='history', permission_classes=[IsAuthenticated])
    def history(self, request, pk=None):
        """查看模型的歷史記錄"""
        instance = self.get_object()
        history_records = instance.history.all().order_by('-history_date')

        if history_records.exists():
            model_class = type(history_records.first())
            serializer_class = type(
                'DynamicHistoricalRecordSerializer',
                (HistoricalRecordSerializer,),
                {'Meta': type('Meta', (), {'model': model_class, 'fields': '__all__'})}
            )
            serializer = serializer_class(history_records, many=True)
        else:
            serializer = HistoricalRecordSerializer(history_records, many=True)

        page = self.paginate_queryset(history_records)
        if page is not None:
            return self.get_paginated_response(serializer.data)

        return Response(serializer.data)


class MaterialCategoryViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """物料類別視圖集"""
    queryset = MaterialCategory.objects.all()
    serializer_class = MaterialCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = MaterialCategoryFilter
    search_fields = ['name', 'description']
    
    def get_serializer_class(self):
        if self.action == 'tree':
            return MaterialCategoryTreeSerializer
        return MaterialCategorySerializer
    
    @action(detail=False, methods=['get'], url_name='tree', permission_classes=[IsAuthenticated])
    def tree(self, request):
        """獲取樹狀結構的物料類別數據"""
        # 僅獲取頂層類別（無父類別的）
        root_categories = MaterialCategory.objects.filter(parent__isnull=True)
        serializer = MaterialCategoryTreeSerializer(root_categories, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_name='items', permission_classes=[IsAuthenticated])
    def items(self, request, pk=None):
        """獲取指定物料類別下的所有品號"""
        category = self.get_object()
        items = Item.objects.filter(material_category=category)
        page = self.paginate_queryset(items)
        if page is not None:
            serializer = ItemSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ItemSerializer(items, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_name='distribution', permission_classes=[IsAuthenticated])
    def distribution(self, request):
        """獲取物料類別分布統計"""
        stats = []
        total_count = Item.objects.count()
        
        if total_count == 0:
            return Response([])
        
        categories = MaterialCategory.objects.annotate(count=Count('items'))
        
        for category in categories:
            percentage = (category.count / total_count) * 100 if total_count > 0 else 0
            
            stats.append({
                'category_name': category.name,
                'item_count': category.count,
                'percentage': round(percentage, 2)
            })
        
        serializer = MaterialCategoryItemCountSerializer(stats, many=True)
        return Response(serializer.data)


class CategoryViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """商品類別視圖集"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']
    
    def get_serializer_class(self):
        if self.action == 'tree':
            return CategoryTreeSerializer
        return CategorySerializer
    
    @action(detail=False, methods=['get'], url_name='tree', permission_classes=[IsAuthenticated])
    def tree(self, request):
        """獲取樹狀結構的類別數據"""
        # 僅獲取頂層類別（無父類別的）
        root_categories = Category.objects.filter(parent__isnull=True)
        serializer = CategoryTreeSerializer(root_categories, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_name='products', permission_classes=[IsAuthenticated])
    def products(self, request, pk=None):
        """獲取指定類別下的所有商品"""
        category = self.get_object()
        # 注意：這裡需要檢查Product模型與Category的關係
        # 假設Product和Category是多對一關係，且外鍵名為'category'
        products = Product.objects.filter(category=category)
        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)


class ItemViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """品號視圖集"""
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ItemFilter
    search_fields = ['item_code', 'name', 'specification']
    ordering_fields = ['item_code', 'name', 'create_time', 'update_time']
    ordering = ['item_code']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ItemCreateUpdateSerializer
        return ItemSerializer
    
    @action(detail=False, methods=['get'], url_name='material_category_distribution', permission_classes=[IsAuthenticated])
    def material_category_distribution(self, request):
        """獲取物料類別分布統計"""
        return MaterialCategoryViewSet.as_view({'get': 'distribution'})(request)
    
    @action(detail=True, methods=['get'], url_name='batches', permission_classes=[IsAuthenticated])
    def batches(self, request, pk=None):
        """獲取品號的批號列表"""
        item = self.get_object()
        batches = Batch.objects.filter(item=item)
        page = self.paginate_queryset(batches)
        if page is not None:
            serializer = BatchListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = BatchListSerializer(batches, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_name='used_in_products', permission_classes=[IsAuthenticated])
    def used_in_products(self, request, pk=None):
        """獲取使用此品號的產品列表"""
        item = self.get_object()
        # 通過ProductItemRelation找到使用此品號的所有產品
        product_relations = ProductItemRelation.objects.filter(item=item)
        products = [relation.product for relation in product_relations]
        
        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)


class BatchViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """批號視圖集"""
    queryset = Batch.objects.all()
    serializer_class = BatchListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = BatchFilter
    search_fields = ['item__item_code', 'batch_number', 'warehouse', 'location']
    ordering_fields = ['batch_number', 'warehouse', 'quantity', 'expiry_date', 'create_time']
    ordering = ['expiry_date', 'batch_number']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BatchDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return BatchCreateUpdateSerializer
        return BatchListSerializer
    
    @action(detail=False, methods=['get'], url_name='expiring_soon', permission_classes=[IsAuthenticated])
    def expiring_soon(self, request):
        """獲取即將過期的批號"""
        from django.utils import timezone
        days = int(request.query_params.get('days', 30))
        today = timezone.now().date()
        expiry_date = today + timezone.timedelta(days=days)
        
        batches = Batch.objects.filter(
            expiry_date__lte=expiry_date,
            expiry_date__gt=today,
            state='active'
        ).order_by('expiry_date')
        
        page = self.paginate_queryset(batches)
        if page is not None:
            serializer = BatchListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = BatchListSerializer(batches, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_name='warehouse_stats', permission_classes=[IsAuthenticated])
    def warehouse_stats(self, request):
        """獲取倉庫庫存統計"""
        warehouse_stats = Batch.objects.values('warehouse').annotate(
            total_quantity=Sum('quantity'),
            product_count=Count('item', distinct=True),
            batch_count=Count('id')
        ).order_by('-total_quantity')
        
        serializer = WarehouseStockSerializer(warehouse_stats, many=True)
        return Response(serializer.data)

class ProductItemRelationViewSet(TrackedAPIView, ModelHistoryViewMixin):
    queryset = ProductItemRelation.objects.all()
    serializer_class = ProductItemRelationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'item', 'batch']
