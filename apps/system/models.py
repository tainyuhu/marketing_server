from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.base import Model
import django.utils.timezone as timezone
from django.db.models.query import QuerySet

from utils.model import SoftModel, BaseModel
from simple_history.models import HistoricalRecords



class Position(BaseModel):
    """
    職位
    """
    name = models.CharField('名稱', max_length=32, unique=True)
    description = models.CharField('描述', max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = '職位'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Permission(SoftModel):
    """
    功能權限
    """
    menu_type_choices = (
        ('目錄', '目錄'),
        ('菜單', '菜單'),
        ('接口', '接口')
    )
    name = models.CharField('名称', max_length=30)
    type = models.CharField('类型', max_length=20,
                            choices=menu_type_choices, default='接口')
    is_frame = models.BooleanField('外部链接', default=False)
    sort = models.IntegerField('排序标记', default=1)
    parent = models.ForeignKey('self', null=True, blank=True,
                            on_delete=models.SET_NULL, verbose_name='父')
    method = models.CharField('方法/代号', max_length=50, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = '功能权限表'
        verbose_name_plural = verbose_name
        ordering = ['sort']


class Organization(SoftModel):
    """
    群組
    """
    organization_type_choices = (
        ('root', 'root'),
        ('group', 'group')
    )
    name = models.CharField('名稱', max_length=60)
    type = models.CharField('類型', max_length=20,
                            choices=organization_type_choices, default='group')
    parent = models.ForeignKey('self', null=True, blank=True,
                            on_delete=models.SET_NULL, verbose_name='父')

    class Meta:
        verbose_name = '群組'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Role(SoftModel):
    """
    角色
    """
    data_type_choices = (
        ('全部', '全部'),
        ('自定義', '自定義'),
        ('同级及以下', '同级及以下'),
        ('本级及以下', '本级及以下'),
        ('本级', '本级'),
        ('僅本人', '僅本人')
    )
    name = models.CharField('角色', max_length=32, unique=True)
    perms = models.ManyToManyField(Permission, blank=True, verbose_name='功能权限')
    datas = models.CharField('数据权限', max_length=50,
                             choices=data_type_choices, default='僅本人')
    depts = models.ManyToManyField(
        Organization, blank=True, verbose_name='权限范围', related_name='roles')
    description = models.CharField('描述', max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = '角色'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    使用者
    """
    # 基本資料
    avatar = models.CharField(
        '大頭貼', default='/media/default/avatar.png', max_length=255, null=True, blank=True)
    name = models.CharField('姓名', max_length=20, null=True, blank=True)
    gender = models.CharField('性別', max_length=10, choices=[
        ('M', '男'),
        ('F', '女'),
    ],null=True, blank=True)
    age = models.IntegerField('年齡',null=True, blank=True)
    # 公司資料
    company = models.CharField('公司', max_length=100,null=True, blank=True)
    department = models.CharField('部門', max_length=50,null=True, blank=True)
    position = models.ManyToManyField(Position, verbose_name='職位', blank=True)
    dept = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='群組')
    # 聯絡資訊
    phone = models.CharField('手機號碼', max_length=11,
                             null=True, blank=True, unique=True)
    address = models.CharField('常用地址', max_length=200,null=True, blank=True)
    # 員工資訊
    hire_date = models.DateField('入職日期',null=True, blank=True)
    employee_status = models.CharField('員工狀態', max_length=20, choices=[
        ('active', '在職'),
        ('leave', '離職'),
    ],null=True, blank=True)
    roles = models.ManyToManyField(Role, blank=True, verbose_name='角色')
    
    nickname = models.CharField('暱稱', max_length=30, null=True, blank=True)
    birthday = models.DateField('生日', null=True, blank=True)
    personality_traits = models.CharField("人格特質", max_length=255, null=True, blank=True)
    mailing_address_1 = models.CharField("通訊地址一", max_length=255, null=True, blank=True)
    mailing_address_2 = models.CharField("通訊地址二", max_length=255, null=True, blank=True)

    # LINE 相關
    is_line_bound = models.BooleanField('是否綁定LINE', default=False)
    line_bind_time = models.DateTimeField('LINE綁定時間', null=True, blank=True)
    line_id = models.CharField('LINE ID', max_length=100, null=True, blank=True, unique=True)

    class Meta:
        verbose_name = '使用者訊息'
        verbose_name_plural = verbose_name
        ordering = ['id']
        
    def __str__(self):
        return self.username

class DictType(SoftModel):
    """
    数据字典类型
    """
    name = models.CharField('名称', max_length=30)
    code = models.CharField('代号', unique=True, max_length=30)
    parent = models.ForeignKey('self', null=True, blank=True,
                            on_delete=models.SET_NULL, verbose_name='父')

    class Meta:
        verbose_name = '字典类型'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Dict(SoftModel):
    """
    数据字典
    """
    name = models.CharField('名称', max_length=60)
    code = models.CharField('编号', max_length=30, null=True, blank=True)
    description = models.TextField('描述', blank=True, null=True)
    type = models.ForeignKey(
        DictType, on_delete=models.CASCADE, verbose_name='类型')
    sort = models.IntegerField('排序', default=1)
    parent = models.ForeignKey('self', null=True, blank=True,
                            on_delete=models.SET_NULL, verbose_name='父')
    is_used = models.BooleanField('是否有效', default=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = '字典'
        verbose_name_plural = verbose_name
        unique_together = ('name', 'is_used', 'type')

    def __str__(self):
        return self.name

class CommonAModel(SoftModel):
    """
    业务用基本表A,包含create_by, update_by字段
    """
    create_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='创建人', related_name= '%(class)s_create_by')
    update_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='最后编辑人', related_name= '%(class)s_update_by')

    class Meta:
        abstract = True

class CommonBModel(SoftModel):
    """
    业务用基本表B,包含create_by, update_by, belong_dept字段
    """
    create_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='创建人', related_name = '%(class)s_create_by')
    update_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='最后编辑人', related_name = '%(class)s_update_by')
    belong_dept = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='所属部门', related_name= '%(class)s_belong_dept')

    class Meta:
        abstract = True


class File(CommonAModel):
    """
    文件存储表,业务表根据具体情况选择是否外键关联
    """
    name = models.CharField('名称', max_length=100, null=True, blank=True)
    size = models.IntegerField('文件大小', default=1, null=True, blank=True)
    file = models.FileField('文件', upload_to='%Y/%m/%d/')
    type_choices = (
        ('文档', '文档'),
        ('视频', '视频'),
        ('音频', '音频'),
        ('图片', '图片'),
        ('其它', '其它')
    )
    mime = models.CharField('文件格式', max_length=120, null=True, blank=True)
    type = models.CharField('文件类型', max_length=50, choices=type_choices, default='文档')
    path = models.CharField('地址', max_length=200, null=True, blank=True)

    class Meta:
        verbose_name = '文件库'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name
    
class VerificationCode(BaseModel):
    """
    驗證碼記錄
    """
    MAX_ATTEMPTS = 3  # 定義最大嘗試次數
    employee = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        verbose_name='員工'
    )
    code = models.CharField(
        max_length=6,
        verbose_name='驗證碼'
    )
    is_used = models.BooleanField(
        default=False,
        verbose_name='是否已使用'
    )
    is_expired = models.BooleanField(
        default=False,
        verbose_name='是否已過期'
    )
    expires_at = models.DateTimeField(
        verbose_name='過期時間'
    )
    attempt_count = models.IntegerField(
        default=0,
        verbose_name='嘗試次數'
    )

    class Meta:
        verbose_name = '驗證碼'
        verbose_name_plural = verbose_name
        ordering = ['-create_time']

    def increase_attempt(self):
        """
        增加嘗試次數並檢查是否超過限制
        """
        self.attempt_count += 1
        if self.attempt_count >= self.MAX_ATTEMPTS:
            self.is_expired = True
        self.save()
        return self.attempt_count >= self.MAX_ATTEMPTS
    def is_expired_now(self):
        """
        檢查驗證碼是否已過期
        """
        return timezone.now() > self.expires_at or self.is_expired
    
    def mark_expired_if_needed(self):
        """
        檢查並標記過期狀態
        """
        if self.is_expired_now() and not self.is_expired:
            self.is_expired = True
            self.save()
        return self.is_expired

    def is_valid(self):
        """
        檢查驗證碼是否有效
        """
        return not self.is_used and not self.is_expired_now() and self.attempt_count < self.MAX_ATTEMPTS