from rest_framework import serializers
from django.utils import timezone
from ..models.customer import (
    CustomerServiceConfig,
    CustomerServiceRequest,
    CustomerServiceMessage,
    FAQ
)


class CustomerServiceConfigSerializer(serializers.ModelSerializer):
    """客服系統設定序列化器"""
    
    class Meta:
        model = CustomerServiceConfig
        fields = [
            'id', 'business_hours_start', 'business_hours_end', 'business_days',
            'customer_service_phone', 'customer_service_email',
            'auto_reply_enabled', 'auto_reply_message', 'notification_email',
            'create_time', 'update_time'
        ]
        read_only_fields = ['id', 'create_time', 'update_time']


class FAQSerializer(serializers.ModelSerializer):
    """常見問題序列化器"""
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = FAQ
        fields = [
            'id', 'category', 'category_display', 'question', 'answer',
            'is_published', 'sort_order', 'create_time', 'update_time'
        ]
        read_only_fields = ['id', 'create_time', 'update_time']


class CustomerServiceMessageSerializer(serializers.ModelSerializer):
    """客服訊息序列化器"""
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    
    class Meta:
        model = CustomerServiceMessage
        fields = [
            'id', 'service_request', 'is_from_staff', 'sender', 'sender_name', 
            'content', 'attachment_url', 'attachment_name', 'create_time'
        ]
        read_only_fields = ['id', 'create_time']


class CustomerServiceRequestListSerializer(serializers.ModelSerializer):
    """客服請求列表序列化器"""
    username = serializers.CharField(source='user.username', read_only=True)
    request_type_display = serializers.CharField(source='get_request_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True, allow_null=True)
    message_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomerServiceRequest
        fields = [
            'id', 'user', 'username', 'order', 'order_number',
            'request_type', 'request_type_display', 'content',
            'status', 'status_display', 'assigned_to', 'assigned_to_name',
            'message_count', 'last_reply_time', 'create_time'
        ]
        read_only_fields = ['id', 'username', 'request_type_display', 'status_display', 
                          'order_number', 'assigned_to_name', 'message_count', 
                          'last_reply_time', 'create_time']
    
    def get_message_count(self, obj):
        return obj.messages.count()


class CustomerServiceRequestDetailSerializer(serializers.ModelSerializer):
    """客服請求詳情序列化器"""
    username = serializers.CharField(source='user.username', read_only=True)
    request_type_display = serializers.CharField(source='get_request_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True, allow_null=True)
    messages = CustomerServiceMessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = CustomerServiceRequest
        fields = [
            'id', 'user', 'username', 'order', 'order_number',
            'request_type', 'request_type_display', 'content',
            'status', 'status_display', 'assigned_to', 'assigned_to_name',
            'last_reply_time', 'closed_time', 'staff_notes',
            'messages', 'create_time', 'update_time'
        ]
        read_only_fields = ['id', 'username', 'request_type_display', 'status_display', 'order_number', 
                          'assigned_to_name', 'last_reply_time', 'closed_time', 
                          'messages', 'create_time', 'update_time']


class CustomerServiceRequestCreateSerializer(serializers.ModelSerializer):
    """客服請求創建序列化器"""
    
    class Meta:
        model = CustomerServiceRequest
        fields = [
            'order', 'request_type', 'content'
        ]
    
    def create(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("用戶未認證")
        
        # 設置當前用戶為請求用戶
        validated_data['user'] = request.user
        
        # 創建客服請求
        service_request = CustomerServiceRequest.objects.create(**validated_data)
        
        # 檢查是否啟用自動回覆
        try:
            config = CustomerServiceConfig.objects.first()
            if config and config.auto_reply_enabled and config.auto_reply_message:
                # 創建系統自動回覆消息
                CustomerServiceMessage.objects.create(
                    service_request=service_request,
                    is_from_staff=True,
                    content=config.auto_reply_message,
                    sender=None  # 系統自動回覆，無特定發送者
                )
                
                # 更新最後回覆時間
                service_request.last_reply_time = timezone.now()
                service_request.status = 'in_progress'
                service_request.save()
        except Exception as e:
            # 自動回覆失敗不影響請求創建
            pass
            
        return service_request


class CustomerServiceMessageCreateSerializer(serializers.ModelSerializer):
    """客服訊息創建序列化器"""
    
    class Meta:
        model = CustomerServiceMessage
        fields = [
            'service_request', 'content', 'attachment_url', 'attachment_name'
        ]
    
    def create(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("用戶未認證")
        
        service_request = validated_data.get('service_request')
        
        # 檢查用戶權限
        is_staff = request.user.is_staff
        
        # 如果是普通用戶，確認是其自己的請求
        if not is_staff and service_request.user != request.user:
            raise serializers.ValidationError("無權限回覆此請求")
        
        # 設置發送者信息
        validated_data['sender'] = request.user
        validated_data['is_from_staff'] = is_staff
        
        # 創建訊息
        message = CustomerServiceMessage.objects.create(**validated_data)
        
        # 更新請求狀態和最後回覆時間
        service_request.last_reply_time = timezone.now()
        
        # 如果是客服回覆，狀態變為處理中
        if is_staff:
            service_request.status = 'in_progress'
            service_request.assigned_to = request.user
        else:
            # 如果是用戶回覆，狀態變為待處理
            service_request.status = 'pending'
        
        service_request.save()
        
        return message


class CustomerServiceRequestStatusUpdateSerializer(serializers.ModelSerializer):
    """客服請求狀態更新序列化器"""
    
    class Meta:
        model = CustomerServiceRequest
        fields = ['status', 'staff_notes']
    
    def update(self, instance, validated_data):
        request = self.context.get('request')
        
        # 只有管理員可以更新狀態
        if not request or not request.user.is_staff:
            raise serializers.ValidationError("只有客服人員可以更新狀態")
        
        status = validated_data.get('status')
        
        # 如果狀態變更為已關閉，記錄關閉時間
        if status == 'closed' and instance.status != 'closed':
            instance.closed_time = timezone.now()
        
        # 更新狀態和備註
        instance.status = status
        instance.staff_notes = validated_data.get('staff_notes', instance.staff_notes)
        
        # 如果分配給自己處理
        instance.assigned_to = request.user
        
        instance.save()
        return instance