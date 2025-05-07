from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.utils import timezone

from ..models.customer import (
    CustomerServiceConfig,
    CustomerServiceRequest,
    CustomerServiceMessage,
    FAQ
)
from ..serializers.customer import (
    CustomerServiceConfigSerializer,
    CustomerServiceRequestListSerializer,
    CustomerServiceRequestDetailSerializer,
    CustomerServiceRequestCreateSerializer,
    CustomerServiceRequestStatusUpdateSerializer,
    CustomerServiceMessageSerializer,
    CustomerServiceMessageCreateSerializer,
    FAQSerializer
)


class CustomerServiceConfigViewSet(viewsets.ModelViewSet):
    """客服系統設定視圖集"""
    queryset = CustomerServiceConfig.objects.all()
    serializer_class = CustomerServiceConfigSerializer
    permission_classes = [IsAdminUser]  # 只有管理員可訪問

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def current(self, request):
        """獲取當前客服系統設定"""
        config = CustomerServiceConfig.objects.first()
        if not config:
            config = CustomerServiceConfig.objects.create()  # 創建默認配置
        
        serializer = self.get_serializer(config)
        
        # 檢查當前是否在上班時間
        now = timezone.now()
        current_time = now.time()
        current_day = str(now.weekday() + 1)  # 將Python的weekday格式(0-6)轉換為1-7格式
        
        # 解析營業日
        business_days = config.business_days.split(',')
        
        is_business_hours = (
            current_day in business_days and
            config.business_hours_start <= current_time <= config.business_hours_end
        )
        
        # 混合數據返回
        data = {
            'config': serializer.data,
            'is_business_hours': is_business_hours,
            'current_time': current_time.strftime('%H:%M:%S'),
            'current_day': current_day
        }
        
        return Response(data)


class FAQViewSet(viewsets.ModelViewSet):
    """常見問題視圖集"""
    queryset = FAQ.objects.filter(is_published=True)
    serializer_class = FAQSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['category']
    search_fields = ['question', 'answer']

    def get_permissions(self):
        """
        根據操作設置權限:
        - 列表和檢索: 所有已認證用戶
        - 創建、更新和刪除: 只有管理員
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    @action(detail=False, methods=['get'], url_path='by-category')
    def by_category(self, request):
        """按分類獲取已分組的FAQ"""
        faqs = FAQ.objects.filter(is_published=True).order_by('category', 'sort_order')
        
        # 按分類分組
        grouped_data = {}
        for faq in faqs:
            category = faq.get_category_display()
            if category not in grouped_data:
                grouped_data[category] = []
            
            serializer = FAQSerializer(faq)
            grouped_data[category].append(serializer.data)
        
        return Response(grouped_data)


class CustomerServiceRequestViewSet(viewsets.ModelViewSet):
    """客服請求視圖集"""
    queryset = CustomerServiceRequest.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'request_type']
    search_fields = ['content', 'user__username', 'order__order_number']
    ordering_fields = ['create_time', 'last_reply_time', 'status']
    ordering = ['-create_time']

    def get_queryset(self):
        """
        過濾查詢集:
        - 普通用戶只能查看自己的請求
        - 管理員可以查看所有請求
        """
        user = self.request.user
        if user.is_staff:
            return CustomerServiceRequest.objects.all()
        return CustomerServiceRequest.objects.filter(user=user)

    def get_serializer_class(self):
        """根據操作選擇序列化器"""
        if self.action == 'list':
            return CustomerServiceRequestListSerializer
        elif self.action == 'create':
            return CustomerServiceRequestCreateSerializer
        elif self.action == 'update_status':
            return CustomerServiceRequestStatusUpdateSerializer
        return CustomerServiceRequestDetailSerializer
    
    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        """更新客服請求狀態 (僅限管理員)"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # 返回更新後的完整對象
        detail_serializer = CustomerServiceRequestDetailSerializer(instance)
        return Response(detail_serializer.data)
    
    @action(detail=False, methods=['get'], url_path='my-requests')
    def my_requests(self, request):
        """獲取當前用戶的客服請求"""
        queryset = CustomerServiceRequest.objects.filter(user=request.user).order_by('-create_time')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CustomerServiceRequestListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CustomerServiceRequestListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='pending', permission_classes=[IsAdminUser])
    def pending_requests(self, request):
        """獲取所有待處理的客服請求 (僅限管理員)"""
        queryset = CustomerServiceRequest.objects.filter(status='pending').order_by('-create_time')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CustomerServiceRequestListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CustomerServiceRequestListSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='stats', permission_classes=[IsAdminUser])
    def request_stats(self, request):
        """獲取客服請求統計 (僅限管理員)"""
        # 按狀態統計
        status_stats = {}
        for status, _ in CustomerServiceRequest.STATUS_CHOICES:
            count = CustomerServiceRequest.objects.filter(status=status).count()
            status_stats[status] = count
        
        # 按類型統計
        type_stats = {}
        for req_type, _ in CustomerServiceRequest.REQUEST_TYPES:
            count = CustomerServiceRequest.objects.filter(request_type=req_type).count()
            type_stats[req_type] = count
        
        # 總數和未處理數
        total_count = CustomerServiceRequest.objects.count()
        unhandled_count = CustomerServiceRequest.objects.filter(status='pending').count()
        
        return Response({
            'total_count': total_count,
            'unhandled_count': unhandled_count,
            'status_stats': status_stats,
            'type_stats': type_stats
        })


class CustomerServiceMessageViewSet(viewsets.ModelViewSet):
    """客服訊息視圖集"""
    queryset = CustomerServiceMessage.objects.all()
    serializer_class = CustomerServiceMessageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        過濾查詢集:
        - 普通用戶只能查看與自己相關的訊息
        - 管理員可以查看所有訊息
        """
        user = self.request.user
        if user.is_staff:
            return CustomerServiceMessage.objects.all()
        
        # 查詢用戶關聯的客服請求
        user_requests = CustomerServiceRequest.objects.filter(user=user)
        return CustomerServiceMessage.objects.filter(service_request__in=user_requests)
    
    def get_serializer_class(self):
        """根據操作選擇序列化器"""
        if self.action == 'create':
            return CustomerServiceMessageCreateSerializer
        return CustomerServiceMessageSerializer
    
    @action(detail=False, methods=['post'], url_path='reply')
    def create_reply(self, request):
        """創建回覆訊息"""
        serializer = CustomerServiceMessageCreateSerializer(
            data=request.data, 
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # 返回更新後的訊息
        response_serializer = CustomerServiceMessageSerializer(serializer.instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_path='by-request/(?P<request_id>[^/.]+)')
    def messages_by_request(self, request, request_id=None):
        """獲取指定客服請求的所有訊息"""
        # 檢查權限
        user = request.user
        try:
            service_request = CustomerServiceRequest.objects.get(pk=request_id)
            if not user.is_staff and service_request.user != user:
                return Response(
                    {"error": "您沒有權限查看此請求的訊息"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            messages = CustomerServiceMessage.objects.filter(
                service_request=service_request
            ).order_by('create_time')
            
            serializer = CustomerServiceMessageSerializer(messages, many=True)
            return Response(serializer.data)
            
        except CustomerServiceRequest.DoesNotExist:
            return Response(
                {"error": "找不到指定的客服請求"}, 
                status=status.HTTP_404_NOT_FOUND
            )