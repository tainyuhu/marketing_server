from django.db import models
from django.conf import settings
from utils.model import SoftModel, BaseModel
from simple_history.models import HistoricalRecords

class CustomerServiceConfig(BaseModel):
    """客服系統基本設定"""
    business_hours_start = models.TimeField("上班時間開始", default="09:00")
    business_hours_end = models.TimeField("上班時間結束", default="18:00")
    business_days = models.CharField("營業日", max_length=20, default="1,2,3,4,5",
                                  help_text="以逗號分隔的星期數字，0代表星期日")
    
    customer_service_phone = models.CharField("客服電話", max_length=20, default="0800-123-456")
    customer_service_email = models.EmailField("客服電子郵件", default="service@example.com")
    
    auto_reply_enabled = models.BooleanField("啟用自動回覆", default=True)
    auto_reply_message = models.TextField("自動回覆訊息", 
                                        default="感謝您的留言，我們會在一個工作天內回覆您。")
    
    notification_email = models.EmailField("通知電子郵件", default="service@example.com",
                                        help_text="有新客服請求時通知此信箱")
    
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "客服系統設定"
        verbose_name_plural = "客服系統設定"
        db_table = "v1_wms_customer_service_config"
    
    def __str__(self):
        return f"客服系統設定 ({self.business_hours_start}-{self.business_hours_end})"


class CustomerServiceRequest(SoftModel):
    """客服請求記錄模型"""
    REQUEST_TYPES = [
        ('order', '訂單問題'),
        ('delivery', '配送問題'),
        ('return', '退換貨'),
        ('product', '產品諮詢'),
        ('other', '其他'),
    ]
    
    STATUS_CHOICES = [
        ('pending', '待處理'),
        ('in_progress', '處理中'),
        ('resolved', '已解決'),
        ('closed', '已關閉'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                           related_name='service_requests', verbose_name="用戶")
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, 
                            related_name='service_requests', verbose_name="相關訂單",
                            null=True, blank=True)
    request_type = models.CharField("問題類型", max_length=20, choices=REQUEST_TYPES)
    content = models.TextField("初始留言內容")
    status = models.CharField("處理狀態", max_length=20, choices=STATUS_CHOICES, default='pending')
    
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  related_name='assigned_requests', verbose_name="處理人員",
                                  null=True, blank=True)
    
    last_reply_time = models.DateTimeField("最後回覆時間", null=True, blank=True)
    closed_time = models.DateTimeField("關閉時間", null=True, blank=True)
    
    staff_notes = models.TextField("內部備註", null=True, blank=True)
    
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "客服請求"
        verbose_name_plural = "客服請求"
        db_table = "v1_wms_customer_service_request"
        ordering = ['status', '-create_time']
    
    def __str__(self):
        return f"{self.user.username} - {self.get_request_type_display()} ({self.get_status_display()})"


class CustomerServiceMessage(BaseModel):
    """客服對話訊息模型"""
    service_request = models.ForeignKey(CustomerServiceRequest, on_delete=models.CASCADE,
                                       related_name='messages', verbose_name="客服請求")
    is_from_staff = models.BooleanField("是否來自客服人員", default=False)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             related_name='cs_messages', verbose_name="發送者",
                             null=True)
    content = models.TextField("訊息內容")
    
    # 附件相關欄位
    attachment_url = models.URLField("附件URL", null=True, blank=True)
    attachment_name = models.CharField("附件名稱", max_length=255, null=True, blank=True)
    
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "客服訊息"
        verbose_name_plural = "客服訊息"
        db_table = "v1_wms_customer_service_message"
        ordering = ['service_request', 'create_time']
    
    def __str__(self):
        sender_type = "客服" if self.is_from_staff else "用戶"
        return f"{self.service_request} - {sender_type}訊息 ({self.create_time.strftime('%Y-%m-%d %H:%M')})"


class FAQ(SoftModel):
    """簡易常見問題模型"""
    CATEGORY_CHOICES = [
        ('order', '訂單相關'),
        ('shipping', '配送相關'),
        ('return', '退換貨相關'),
        ('product', '產品相關'),
        ('other', '其他'),
    ]
    
    category = models.CharField("分類", max_length=20, choices=CATEGORY_CHOICES)
    question = models.CharField("問題", max_length=255)
    answer = models.TextField("回答")
    is_published = models.BooleanField("已發布", default=True)
    sort_order = models.IntegerField("排序", default=0)
    
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "常見問題"
        verbose_name_plural = "常見問題"
        db_table = "v1_wms_faq"
        ordering = ['category', 'sort_order']
    
    def __str__(self):
        return f"{self.get_category_display()} - {self.question}"