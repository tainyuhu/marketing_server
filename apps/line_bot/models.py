from django.db import models
from django.utils import timezone
from utils.model import SoftModel
from apps.system.models import User

class LineUser(SoftModel):
    """LINE 用戶模型"""
    user = models.ForeignKey(
        'system.User', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        verbose_name='系統用戶',
        related_name='line_profile'
    )
    line_user_id = models.CharField(max_length=100, verbose_name='LINE User ID')
    display_name = models.CharField(max_length=255, blank=True, verbose_name='顯示名稱')
    status_message = models.TextField(blank=True, null=True, verbose_name='狀態消息')
    picture_url = models.URLField(blank=True, null=True, verbose_name='頭像 URL')
    language = models.CharField(max_length=10, blank=True, null=True, verbose_name='語言設定')
    last_interaction = models.DateTimeField(default=timezone.now, verbose_name='最後互動時間')
    
    def update_last_interaction(self):
        self.last_interaction = timezone.now()
        self.save()
    
    def bind_user(self, user: 'User'):
        """綁定系統用戶"""
        self.user = user
        user.is_line_bound = True
        user.line_bind_time = timezone.now()
        user.line_id = self.line_user_id  # 同步 LINE ID
        
        # 同步用戶資料
        if not user.avatar and self.picture_url:
            user.avatar = self.picture_url
        if not user.name and self.display_name:
            user.name = self.display_name
            
        user.save()
        self.save()

    def unbind_user(self):
        """解除綁定系統用戶"""
        if self.user:
            self.user.is_line_bound = False
            self.user.line_bind_time = None
            self.user.line_id = None  # 清除 LINE ID
            self.user.save()
        self.user = None
        self.save()
    
    def __str__(self):
        if self.user:
            return f"{self.display_name} ({self.user.username})"
        return self.display_name or self.line_user_id
    
    class Meta:
        db_table = 'line_user'
        verbose_name = 'LINE用戶'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['line_user_id']),
            models.Index(fields=['last_interaction']),
        ]
        unique_together = ('line_user_id', 'is_deleted')

class LineMessage(SoftModel):
    """LINE 消息記錄"""
    MESSAGE_TYPES = (
        ('text', '文字'),
        ('image', '圖片'),
        ('video', '視頻'),
        ('audio', '音頻'),
        ('file', '文件'),
        ('location', '位置'),
        ('sticker', '貼圖'),
    )
    
    STATUS_CHOICES = (
        ('pending', '待處理'),
        ('sent', '已發送'),
        ('delivered', '已送達'),
        ('failed', '發送失敗'),
    )
    line_user = models.ForeignKey(LineUser, on_delete=models.CASCADE, verbose_name='LINE用戶')
    message = models.TextField(verbose_name='消息內容')
    message_type = models.CharField(max_length=50, choices=MESSAGE_TYPES, verbose_name='消息類型')
    is_sent = models.BooleanField(default=False, verbose_name='是否為發送')
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='消息狀態'
    )
    send_time = models.DateTimeField(auto_now_add=True, verbose_name='發送時間')
    delivery_time = models.DateTimeField(null=True, blank=True, verbose_name='送達時間')
    error_message = models.TextField(blank=True, null=True, verbose_name='錯誤信息')
    
    def __str__(self):
        return f"{self.line_user} - {self.get_message_type_display()} ({self.send_time.strftime('%Y-%m-%d %H:%M')})"
    
    class Meta:
        db_table = 'line_message'
        verbose_name = 'LINE消息'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['line_user', 'send_time']),
            models.Index(fields=['message_type']),
            models.Index(fields=['status']),
        ]

class LineMessageAttachment(SoftModel):
    """LINE 消息附件"""
    message = models.ForeignKey(LineMessage, on_delete=models.CASCADE, related_name='attachments')
    file_type = models.CharField(max_length=50, verbose_name='文件類型')
    file_url = models.URLField(verbose_name='文件URL')
    file_size = models.IntegerField(default=0, verbose_name='文件大小')
    content_type = models.CharField(max_length=100, verbose_name='內容類型')
    
    def __str__(self):
        return f"{self.message} - {self.file_type}"
    
    class Meta:
        db_table = 'line_message_attachment'
        verbose_name = 'LINE消息附件'
        verbose_name_plural = verbose_name