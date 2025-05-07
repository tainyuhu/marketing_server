from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from utils.view import TrackedAPIView
from ..models import (
    Activity, ActivityProduct, PromotionRule, PromotionRuleRelation, UserActivityLog
)
from ..serializers import (
    HistoricalRecordSerializer, ActivityListSerializer, ActivityDetailSerializer, 
    ActivityProductSerializer, ActivityProductCreateUpdateSerializer,
    HotSaleActivitySerializer, PromotionRuleSerializer, PromotionRuleRelationSerializer,
    UserActivityLogSerializer
)
from ..filters import ActivityFilter
from ..utils import recalculate_all_activity_product_stock
from .warehouse import ModelHistoryViewMixin


class ActivityViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """活動視圖集"""
    queryset = Activity.objects.all()
    serializer_class = ActivityListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ActivityFilter
    search_fields = ['name', 'description']
    ordering_fields = ['start_date', 'end_date', 'is_popular', 'progress', 'create_time']
    ordering = ['-start_date']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ActivityDetailSerializer
        return ActivityListSerializer
    
    @action(detail=True, methods=['get'], url_name='products', permission_classes=[IsAuthenticated])
    def products(self, request, pk=None):
        """獲取活動的商品列表"""
        activity = self.get_object()
        activity_products = ActivityProduct.objects.filter(activity=activity)
        
        page = self.paginate_queryset(activity_products)
        if page is not None:
            serializer = ActivityProductSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ActivityProductSerializer(activity_products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name='add_product', permission_classes=[IsAuthenticated])
    def add_product(self, request, pk=None):
        """添加商品到活動"""
        activity = self.get_object()
        
        serializer = ActivityProductCreateUpdateSerializer(data={
            'activity': activity.id,
            **request.data
        })
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['delete'], url_name='remove_product', permission_classes=[IsAuthenticated])
    def remove_product(self, request, pk=None):
        """從活動中移除商品"""
        activity = self.get_object()
        product_id = request.data.get('product_id')
        
        if not product_id:
            return Response({'error': '商品ID不能為空'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            activity_product = ActivityProduct.objects.get(activity=activity, product_id=product_id)
            activity_product.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ActivityProduct.DoesNotExist:
            return Response({'error': '該活動中找不到指定商品'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'], url_name='active', permission_classes=[IsAuthenticated])
    def active(self, request):
        """獲取當前有效的活動"""
        now = timezone.now()
        active_activities = Activity.objects.filter(
            start_date__lte=now,
            end_date__gte=now
        ).order_by('end_date')
        
        page = self.paginate_queryset(active_activities)
        if page is not None:
            serializer = ActivityListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ActivityListSerializer(active_activities, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='hot-sale')
    def hot_sale(self, request):
        """獲取熱銷活動"""
        now = timezone.now()

        hot_activity = Activity.objects.filter(
            is_popular=True,
            start_date__lte=now,
            end_date__gte=now,
            is_deleted=False
        ).order_by('-progress').first()

        if not hot_activity:
            return Response({"data": None}, status=status.HTTP_200_OK)  # 👈 重點：空資料 + 200

        serializer = HotSaleActivitySerializer(hot_activity)
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)


    @action(detail=False, methods=['get'], url_path='product_promotion', permission_classes=[IsAuthenticated])
    def product_promotion(self, request):
        """取得促銷活動列表"""
        queryset = Activity.objects.filter(activity_type='product_promotion', is_deleted=False).order_by('start_date')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ActivityListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ActivityListSerializer(queryset, many=True)
        return Response(serializer.data)


class ActivityProductViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """活動商品視圖集"""
    queryset = ActivityProduct.objects.all()
    serializer_class = ActivityProductSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ActivityProductCreateUpdateSerializer
        return ActivityProductSerializer

    @action(detail=True, methods=['get'], url_name='calculated_stock', permission_classes=[IsAuthenticated])
    def calculated_stock(self, request, pk=None):
        """
        Get the calculated stock based on component availability
        """
        activity_product = self.get_object()
        calculated_stock = activity_product.calculate_available_stock()
        
        return Response({
            'id': activity_product.id,
            'current_stock': activity_product.stock,
            'calculated_stock': calculated_stock,
            'is_consistent': activity_product.stock == calculated_stock
        })
    
    @action(detail=True, methods=['post'], url_name='sync_stock', permission_classes=[IsAuthenticated])
    def sync_stock(self, request, pk=None):
        """
        Synchronize the stock with calculated availability
        """
        activity_product = self.get_object()
        old_stock = activity_product.stock
        calculated_stock = activity_product.calculate_available_stock()
        
        if old_stock != calculated_stock:
            # Use update to avoid triggering post_save signal
            ActivityProduct.objects.filter(id=activity_product.id).update(stock=calculated_stock)
            activity_product.refresh_from_db()
            
            return Response({
                'id': activity_product.id,
                'old_stock': old_stock,
                'new_stock': calculated_stock,
                'updated': True
            })
        
        return Response({
            'id': activity_product.id,
            'stock': old_stock,
            'updated': False,
            'message': '庫存已經是最新狀態'
        })
    
    @action(detail=False, methods=['post'], url_name='recalculate_all', permission_classes=[IsAuthenticated])
    def recalculate_all(self, request):
        """
        Recalculate stock for all activity products
        """
        updated_count = recalculate_all_activity_product_stock()
        
        return Response({
            'updated_count': updated_count,
            'message': f'成功更新 {updated_count} 個活動商品的庫存'
        })
    
    @action(detail=False, methods=['get'], url_name='stock_report', permission_classes=[IsAuthenticated])
    def stock_report(self, request):
        """
        Get a report of all activity products with stock inconsistencies
        """
        activity_products = ActivityProduct.objects.all()
        inconsistent = []
        
        for ap in activity_products:
            calculated = ap.calculate_available_stock()
            if ap.stock != calculated:
                inconsistent.append({
                    'id': ap.id,
                    'product_name': ap.product.product_name,
                    'activity_name': ap.activity.name,
                    'current_stock': ap.stock,
                    'calculated_stock': calculated
                })
        
        return Response({
            'total_checked': activity_products.count(),
            'inconsistent_count': len(inconsistent),
            'inconsistent_items': inconsistent
        })


class PromotionRuleViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """促銷規則視圖集"""
    queryset = PromotionRule.objects.all()
    serializer_class = PromotionRuleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'rule_type', 'create_time']
    ordering = ['-create_time']
    
    @action(detail=False, methods=['get'], url_name='rule_types', permission_classes=[IsAuthenticated])
    def rule_types(self, request):
        """獲取所有規則類型"""
        rule_types = [
            {'value': 'buy_gift', 'label': '買贈'},
            {'value': 'buy_discount', 'label': '買折扣'},
            {'value': 'order_discount', 'label': '滿額折'},
            {'value': 'order_free_shipping', 'label': '免運'},
        ]
        return Response(rule_types)


class PromotionRuleRelationViewSet(viewsets.ModelViewSet):
    """促銷規則關聯視圖集"""
    queryset = PromotionRuleRelation.objects.all()
    serializer_class = PromotionRuleRelationSerializer
    filterset_fields = ['promotion_rule', 'activity', 'product', 'activity_product', 'is_sitewide', 'is_active', 
                        'product_id', 'activity_product_id']
    ordering = ['-priority', 'id']


class UserActivityLogViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """使用者活動參與紀錄視圖集"""
    queryset = UserActivityLog.objects.all()
    serializer_class = UserActivityLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['user__username', 'activity__name']
    ordering_fields = ['joined_at']
    ordering = ['-joined_at']
    
    def get_queryset(self):
        """依照權限過濾活動參與紀錄"""
        user = self.request.user
        # 如果是管理員，返回所有紀錄
        if user.is_staff:
            return UserActivityLog.objects.all()
        # 否則只返回當前用戶的紀錄
        return UserActivityLog.objects.filter(user=user)
    
    @action(detail=False, methods=['post'], url_name='join_activity', permission_classes=[IsAuthenticated])
    def join_activity(self, request):
        """參與活動"""
        user = request.user
        activity_id = request.data.get('activity_id')
        
        if not activity_id:
            return Response({'error': '活動ID不能為空'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            activity = Activity.objects.get(id=activity_id)
        except Activity.DoesNotExist:
            return Response({'error': '找不到指定的活動'}, status=status.HTTP_404_NOT_FOUND)
        
        # 檢查活動是否有效
        now = timezone.now()
        if not (activity.start_date <= now <= activity.end_date):
            return Response({'error': '活動未開始或已結束'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 檢查是否已參與
        log, created = UserActivityLog.objects.get_or_create(
            user=user,
            activity=activity,
            defaults={'joined_at': now}
        )
        
        if not created:
            return Response({'message': '已經參與此活動'})
        
        return Response({'message': '成功參與活動'}, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'], url_name='receive_gift', permission_classes=[IsAuthenticated])
    def receive_gift(self, request):
        """領取活動贈品"""
        user = request.user
        activity_id = request.data.get('activity_id')
        
        if not activity_id:
            return Response({'error': '活動ID不能為空'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            log = UserActivityLog.objects.get(user=user, activity_id=activity_id)
        except UserActivityLog.DoesNotExist:
            return Response({'error': '您尚未參與此活動'}, status=status.HTTP_404_NOT_FOUND)
        
        if log.received_gift:
            return Response({'error': '已經領取過贈品'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 更新領取狀態
        log.received_gift = True
        log.save()
        
        return Response({'message': '成功領取贈品'})