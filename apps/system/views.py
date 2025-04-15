import logging
from apps.line_bot.views import LineBotApi
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.mixins import (CreateModelMixin, DestroyModelMixin,
                                   ListModelMixin, RetrieveModelMixin,
                                   UpdateModelMixin)
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import (FileUploadParser, JSONParser,
                                    MultiPartParser)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError, ParseError
from apps.line_bot.models import LineUser
from utils.queryset import get_child_queryset2

from .filters import UserFilter
from .mixins import CreateUpdateModelAMixin, OptimizationMixin
from .models import (Dict, DictType, File, Organization, Permission, Position,
                     Role, User, VerificationCode)
from .permission import RbacPermission, get_permission_list
from .permission_data import RbacFilterSet
from .serializers import (DictSerializer, DictTypeSerializer, FileSerializer,
                          OrganizationSerializer, PermissionSerializer,
                          PositionSerializer, RoleSerializer, PTaskSerializer,PTaskCreateUpdateSerializer,
                          UserCreateSerializer, UserListSerializer,
                          UserModifySerializer)
from django.db.models import Count
from django.db import transaction 
from django.contrib.auth.hashers import check_password
from datetime import timedelta
from django.utils import timezone
import random



logger = logging.getLogger('log')
# logger.info('请求成功！ response_code:{}；response_headers:{}；response_body:{}'.format(response_code, response_headers, response_body[:251]))
# logger.error('请求出错-{}'.format(error))

from server.celery import app as celery_app


from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import status
from rest_framework.response import Response
from django.contrib.auth.hashers import check_password
from django.contrib.auth import get_user_model

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # 檢查使用者名稱和密碼
        User = get_user_model()
        try:
            user = User.objects.get(username=attrs.get('username'))
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'error': 'No active account found with the given credentials'
            })
        
        # 檢查密碼哈希是否正確
        if not check_password(attrs.get('password'), user.password):
            raise serializers.ValidationError({
                'error': 'Invalid password'
            })
        
        # 如果通過所有驗證,生成 token
        data = super().validate(attrs)
        
        # 檢查是否為預設密碼，並添加標記
        data['username'] = self.user.username
        data['user_id']= self.user.id
        data['need_change_password'] = (attrs.get('password') == 'sunny6688')
        
        return data

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

class TaskList(APIView):
    permission_classes = ()

    def get(self, requests):
        tasks = list(sorted(name for name in celery_app.tasks if not name.startswith('celery.')))
        return Response(tasks)

class LogoutView(APIView):
    permission_classes = []

    def get(self, request, *args, **kwargs):  # 可将token加入黑名单
        return Response(status=status.HTTP_200_OK)

class PTaskViewSet(OptimizationMixin, ModelViewSet):
    perms_map = {'get': '*', 'post': 'ptask_create',
                 'put': 'ptask_update', 'delete': 'ptask_delete'}
    queryset = PeriodicTask.objects.exclude(name__contains='celery.')
    serializer_class = PTaskSerializer
    search_fields = ['name']
    filterset_fields = ['enabled']
    ordering = ['-pk']

    @action(methods=['put'], detail=True, perms_map={'put':'task_update'},
            url_name='task_toggle')
    def toggle(self, request, pk=None):
        """
        修改启用禁用状态
        """
        obj = self.get_object()
        obj.enabled = False if obj.enabled else True
        obj.save()
        return Response(status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return PTaskSerializer
        return PTaskCreateUpdateSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        timetype = data.get('timetype', None)
        interval_ = data.get('interval_', None)
        crontab_ = data.get('crontab_', None)
        if timetype == 'interval' and interval_:
            data['crontab'] = None
            try:
                interval, _ = IntervalSchedule.objects.get_or_create(**interval_, defaults = interval_)
                data['interval'] = interval.id
            except:
                raise ValidationError('时间策略有误')
        if timetype == 'crontab' and crontab_:
            data['interval'] = None
            try:
                crontab_['timezone'] = 'Asia/Shanghai'
                crontab, _ = CrontabSchedule.objects.get_or_create(**crontab_, defaults = crontab_)
                data['crontab'] = crontab.id
            except:
                raise ValidationError('时间策略有误')
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_200_OK)
    
    def update(self, request, *args, **kwargs):
        data = request.data
        timetype = data.get('timetype', None)
        interval_ = data.get('interval_', None)
        crontab_ = data.get('crontab_', None)
        if timetype == 'interval' and interval_:
            data['crontab'] = None
            try:
                if 'id' in interval_:
                    del interval_['id']
                interval, _ = IntervalSchedule.objects.get_or_create(**interval_, defaults = interval_)
                data['interval'] = interval.id
            except:
                raise ValidationError('时间策略有误')
        if timetype == 'crontab' and crontab_:
            data['interval'] = None
            try:
                crontab_['timezone'] = 'Asia/Shanghai'
                if 'id'in crontab_:
                    del crontab_['id'] 
                crontab, _ = CrontabSchedule.objects.get_or_create(**crontab_, defaults = crontab_)
                data['crontab'] = crontab.id
            except:
                raise ValidationError('时间策略有误')
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_200_OK)


class DictTypeViewSet(ModelViewSet):
    """
    数据字典类型-增删改查
    """
    perms_map = {'get': '*', 'post': 'dicttype_create',
                 'put': 'dicttype_update', 'delete': 'dicttype_delete'}
    queryset = DictType.objects.all()
    serializer_class = DictTypeSerializer
    pagination_class = None
    search_fields = ['name']
    ordering_fields = ['pk']
    ordering = ['pk']


class DictViewSet(ModelViewSet):
    """
    数据字典-增删改查
    """
    perms_map = {'get': '*', 'post': 'dict_create',
                 'put': 'dict_update', 'delete': 'dict_delete'}
    # queryset = Dict.objects.get_queryset(all=True) # 获取全部的,包括软删除的
    queryset = Dict.objects.all()
    filterset_fields = ['type', 'is_used', 'type__code']
    serializer_class = DictSerializer
    search_fields = ['name']
    ordering_fields = ['sort']
    ordering = ['sort']

    def paginate_queryset(self, queryset):
        """
        如果查询参数里没有page但有type或type__code时则不分页,否则请求分页
        也可用utils.pageornot方法
        """
        if self.paginator is None:
            return None
        elif (not self.request.query_params.get('page', None)) and ((self.request.query_params.get('type__code', None)) or (self.request.query_params.get('type', None))):
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

class PositionViewSet(ModelViewSet):
    """
    岗位-增删改查
    """
    perms_map = {'get': '*', 'post': 'position_create',
                 'put': 'position_update', 'delete': 'position_delete'}
    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    pagination_class = None
    search_fields = ['name','description']
    ordering_fields = ['pk']
    ordering = ['pk']


class TestView(APIView):
    perms_map = {'get': 'test_view'}  # 单个API控权
    authentication_classes = []
    permission_classes = []
    def get(self, request, format=None):
        return Response('测试api接口')


class PermissionViewSet(ModelViewSet):
    """
    权限-增删改查
    """
    perms_map = {'get': '*', 'post': 'perm_create',
                 'put': 'perm_update', 'delete': 'perm_delete'}
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    pagination_class = None
    search_fields = ['name']
    ordering_fields = ['sort']
    ordering = ['sort', 'pk']


class OrganizationViewSet(ModelViewSet):
    """
    群組-增删改查
    """
    perms_map = {'get': '*', 'post': 'org_create',
                 'put': 'org_update', 'delete': 'org_delete'}
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    pagination_class = None
    search_fields = ['name', 'type']
    ordering_fields = ['pk']
    ordering = ['pk']

    @action(detail=False, methods=['get'], url_path='user_count')
    def user_count(self, request):
        """
        返回每個群組（包含其子群組）的使用者數量
        """
        organizations = Organization.objects.all()  # 取得所有群組資料
        results = []

        def get_recursive_user_count(org):
            """遞迴計算某個群組及其所有子群組的使用者數量"""
            # 計算直接屬於該群組的使用者數量
            user_count = User.objects.filter(dept=org).count()
            # 查找該群組的所有子群組
            sub_orgs = Organization.objects.filter(parent=org)
            # 遞迴計算所有子群組的使用者數量
            for sub_org in sub_orgs:
                user_count += get_recursive_user_count(sub_org)
            return user_count

        # 遍歷所有群組並計算每個群組的使用者數量
        for org in organizations:
            results.append({
                "id": org.id,
                "name": org.name,
                "parent_id": org.parent_id,
                "user_count": get_recursive_user_count(org),
            })

        return Response(results)

    @action(detail=True, methods=['get'], url_path='users')
    def get_org_users(self, request, pk=None):
        """
        返回指定群組及其子群組的所有使用者清單
        """
        try:
            org = self.get_object()
            results = []
            
            def get_recursive_users(org):
                # 取得直接屬於該群組的使用者
                users = User.objects.filter(dept=org).values(
                    'id', 
                    'username',
                    'name',
                    'email',
                    'phone',
                    'dept_id',
                    'dept__name'  # 包含部門名稱
                )
                user_list = list(users)
                
                # 取得子群組的使用者
                sub_orgs = Organization.objects.filter(parent=org)
                for sub_org in sub_orgs:
                    user_list.extend(get_recursive_users(sub_org))
                
                return user_list
            
            users = get_recursive_users(org)
            
            # 依據使用者 ID 去重
            seen_ids = set()
            unique_users = []
            for user in users:
                if user['id'] not in seen_ids:
                    seen_ids.add(user['id'])
                    unique_users.append(user)
            
            return Response({
                'org_id': org.id,
                'org_name': org.name,
                'users': unique_users
            })
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=400)       


class RoleViewSet(ModelViewSet):
    """
    角色-增删改查
    """
    perms_map = {'get': '*', 'post': 'role_create',
                 'put': 'role_update', 'delete': 'role_delete'}
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    pagination_class = None
    search_fields = ['name']
    ordering_fields = ['pk']
    ordering = ['pk']


class UserViewSet(ModelViewSet):
    """
    用户管理-增删改查
    """
    perms_map = {'get': '*', 'post': 'user_create',
                 'put': 'user_update', 'delete': 'user_delete'}
    queryset = User.objects.all()
    serializer_class = UserListSerializer
    filterset_class = UserFilter
    search_fields = ['username', 'name', 'phone', 'email']
    ordering_fields = ['-pk']

    def perform_destroy(self, instance):
        if instance.is_superuser:
            raise ParseError('不能删除超级用户')
        instance.delete()

    def get_queryset(self):
        queryset = self.queryset
        if hasattr(self.get_serializer_class(), 'setup_eager_loading'):
            queryset = self.get_serializer_class().setup_eager_loading(queryset) 
        dept = self.request.query_params.get('dept', None) 
        if dept:
            deptqueryset = get_child_queryset2(Organization.objects.get(pk=dept))
            queryset = queryset.filter(dept__in=deptqueryset)
        return queryset

    def get_serializer_class(self):
        # 根据请求类型动态变更serializer
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action == 'update':
            return UserModifySerializer
        elif self.action == 'list':
            return UserListSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        """
        創建用戶
        """
        password = request.data.get('password', 'sunny6688')
        role_ids = request.data.get('roles', [])

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            # 創建用戶
            user = serializer.save(password=make_password(password))
            # 設置角色
            user.roles.set(role_ids)

        return Response(serializer.data)

    @action(methods=['put'], detail=False, permission_classes=[IsAuthenticated], # perms_map={'put':'change_password'}
            url_name='change_password')
    def password(self, request, pk=None):
        """
        修改密碼
        """
        user = request.user
        old_password = request.data['old_password']
        if check_password(old_password, user.password):
            new_password1 = request.data['new_password1']
            new_password2 = request.data['new_password2']
            if new_password1 == new_password2:
                user.set_password(new_password2)
                user.save()
                return Response('密碼修改成功!', status=status.HTTP_200_OK)
            else:
                return Response('新密碼兩次輸入不一致!', status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response('舊密碼錯誤!', status=status.HTTP_400_BAD_REQUEST)
        
    @action(methods=['put'], detail=False, url_path='reset', permission_classes=[])
    def reset_password(self, request):
        """重設密碼"""
        employee_id = request.data.get('employeeId')
        new_password = request.data.get('new_password')
        
        if not employee_id or not new_password:
            return Response({
                'success': False,
                'message': '請提供完整資料'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(username=employee_id)
            
            # 檢查是否有通過驗證的驗證碼記錄
            valid_verification = VerificationCode.objects.filter(
                employee=user,
                is_used=True,
                is_expired=False,
                create_time__gte=timezone.now() - timedelta(minutes=10)  # 驗證成功後的有效重設時間
            ).exists()
            
            if not valid_verification:
                return Response({
                    'success': False,
                    'message': '請先進行驗證碼驗證'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 重設密碼
            user.set_password(new_password)
            user.save()
            
            return Response({
                'success': True,
                'message': '密碼重設成功'
            })
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': '找不到該員工編號'
            }, status=status.HTTP_404_NOT_FOUND)

    # perms_map={'get':'*'}, 自定义action控权
    @action(methods=['get'], detail=False, url_name='my_info', permission_classes=[IsAuthenticated])
    def info(self, request, pk=None):
        """
        初始化用户信息
        """
        user = request.user
        perms = get_permission_list(user)

        # 安全處理 LINE Profile
        line_profile = None
        if user.is_line_bound and user.line_id:
            try:
                line_user = LineUser.objects.filter(line_user_id=user.line_id).first()
                if line_user:
                    line_profile = {
                        'display_name': line_user.display_name or '',
                        'picture_url': line_user.picture_url or ''
                    }
            except Exception:
                pass

        # 組裝完整資料
        data = {
            'id': user.id,
            'username': user.username,
            'name': user.name or '',
            'roles': list(user.roles.values_list('name', flat=True)),
            'avatar': user.avatar or '',
            'perms': perms or [],

            'date_joined': user.date_joined.strftime('%Y-%m-%d') if user.date_joined else '',

            # 個人資料欄位
            'email': user.email or '',
            'phone': user.phone or '',
            'gender': user.gender or '',
            'nickname': user.nickname or '',
            'birthday': user.birthday.strftime('%Y-%m-%d') if user.birthday else '',

            # 地址
            'address': user.address or '',
            'mailing_address_1': user.mailing_address_1 or '',
            'mailing_address_2': user.mailing_address_2 or '',

            # LINE 資訊
            'is_line_bound': user.is_line_bound,
            'line_id': user.line_id or '',
            'line_bind_time': user.line_bind_time.isoformat() if user.line_bind_time else None,
            'line_profile': line_profile
        }


        return Response(data)

    @action(methods=['put'], detail=False, url_name='update_profile', permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """
        更新當前用戶的個人資料
        """
        user = request.user
        serializer = UserModifySerializer(user, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': '個人資料更新成功',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'message': '資料驗證失敗',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(methods=['get'], detail=False, url_name='check_line_binding')
    def check_line_binding(self, request):
        """
        檢查用戶是否綁定 LINE 帳號
        """
        username = request.query_params.get('username')
        if not username:
            return Response({
                'message': '請提供工號'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 查找用戶
        user = get_object_or_404(User, username=username)
        
        try:
            # 檢查是否有對應的 LINE 綁定
            line_user = LineUser.objects.get(id=user.line_id)
            return Response({
                'has_line': True,
                'line_user_id': line_user.line_user_id
            })
        except LineUser.DoesNotExist:
            return Response({
                'has_line': False,
                'line_user_id': None
            })

class FileViewSet(CreateModelMixin, DestroyModelMixin, RetrieveModelMixin, ListModelMixin, GenericViewSet):
    """
    文件上传用
    """
    perms_map = None
    permission_classes=[IsAuthenticated]
    parser_classes = [MultiPartParser, JSONParser]
    queryset = File.objects.all()
    serializer_class = FileSerializer
    filterset_fields = ['type']
    search_fields = ['name']
    ordering = ['-create_time']

    def perform_create(self, serializer):
        fileobj = self.request.data.get('file')
        name = fileobj._name
        size = fileobj.size
        mime = fileobj.content_type
        type = '其它'
        if 'image' in mime:
            type = '图片'
        elif 'video' in mime:
            type = '视频'
        elif 'audio' in mime:
            type = '音频'
        elif 'application' or 'text' in mime:
            type = '文档'
        instance = serializer.save(create_by = self.request.user, name=name, size=size, type=type, mime=mime)
        instance.path = settings.MEDIA_URL + instance.file.name
        instance.save()

class ResetPasswordViewSet(ModelViewSet):
    @action(methods=['post'], detail=False, url_path='send-code', permission_classes=[])
    def send_code(self, request):
        """發送驗證碼到 LINE"""
        employee_id = request.data.get('employeeId')
        
        if not employee_id:
            return Response({
                'success': False,
                'message': '請提供工號'
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            # 查找用戶
            user = User.objects.get(username=employee_id)
            
            # 檢查 LINE 綁定狀態
            try:
                line_user = LineUser.objects.get(user=user, is_deleted=False)
            except LineUser.DoesNotExist:
                return Response({
                    'success': False,
                    'message': '此帳號尚未綁定 LINE'
                }, status=status.HTTP_400_BAD_REQUEST)
                
            # 生成6位數驗證碼
            verification_code = ''.join(
                [str(random.randint(0, 9)) for _ in range(6)]
            )
            
            # 建立新的驗證碼記錄
            verification = VerificationCode.objects.create(
                employee=user,
                code=verification_code,
                expires_at=timezone.now() + timedelta(minutes=2)
            )
            
            # 發送 LINE 訊息
            line_bot_api = LineBotApi()
            line_message = f'您的重設密碼驗證碼為：{verification_code}，2分鐘內有效。'
            
            send_result = line_bot_api.push_message(line_user.line_user_id, line_message)
            
            if send_result:
                return Response({
                    'success': True,
                    'message': '驗證碼已發送至您的 LINE'
                })
            else:
                return Response({
                    'success': False,
                    'message': 'LINE訊息發送失敗，請稍後再試'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': '找不到該員工編號'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            return Response({
                'success': False,
                'message': f'發送驗證碼時發生錯誤: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['post'], detail=False, url_path='verify-code', permission_classes=[])
    def verify_code(self, request):
        """驗證碼確認"""
        employee_id = request.data.get('employeeId')
        code = request.data.get('code')
        
        if not employee_id or not code:
            return Response({
                'success': False,
                'message': '請提供工號和驗證碼'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(username=employee_id)
            
            # 找出此使用者所有未使用的驗證碼，並依照建立時間排序
            all_verifications = VerificationCode.objects.filter(
                employee=user,
                is_used=False
            ).order_by('-create_time')

            # 找出最新的驗證碼
            latest_verification = all_verifications.first()
            
            if latest_verification:
                with transaction.atomic():
                    # 先檢查是否過期
                    if latest_verification.is_expired_now():
                        latest_verification.mark_expired_if_needed()
                        return Response({
                            'success': False,
                            'message': '驗證碼已過期'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # 檢查是否為正確的驗證碼
                    if latest_verification.code != code:
                        # 增加嘗試次數，如果超過限制會自動設為過期
                        is_max_attempts = latest_verification.increase_attempt()
                        
                        message = '驗證碼錯誤'
                        if is_max_attempts:
                            message = '驗證碼已失效，嘗試次數過多'
                            
                        return Response({
                            'success': False,
                            'message': message
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # 驗證成功，標記為已使用
                    latest_verification.is_used = True
                    latest_verification.save()
                
                return Response({
                    'success': True,
                    'message': '驗證成功',
                    'token': self._generate_reset_token(user)
                })
            else:
                return Response({
                    'success': False,
                    'message': '沒有可用的驗證碼'
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': '找不到該員工編號'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(methods=['post'], detail=False, url_path='reset-password', permission_classes=[])
    def reset_password(self, request):
        """重設密碼"""
        reset_token = request.data.get('token')
        new_password = request.data.get('newPassword')
        
        if not reset_token or not new_password:
            return Response({
                'success': False,
                'message': '請提供重設令牌和新密碼'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 解析重設令牌並找到對應用戶
            user_id = self._validate_reset_token(reset_token)
            if not user_id:
                return Response({
                    'success': False,
                    'message': '重設令牌無效或已過期'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = User.objects.get(id=user_id)
            
            # 密碼複雜度檢查
            if len(new_password) < 8:
                return Response({
                    'success': False,
                    'message': '密碼長度必須至少為8個字符'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 設置新密碼
            user.set_password(new_password)
            user.save()
            
            # 成功重設密碼後，發送LINE通知
            try:
                line_user = LineUser.objects.get(user=user, is_deleted=False)
                line_bot_api = LineBotApi()
                line_message = '您的密碼已成功重設。如果這不是您本人操作，請立即聯繫系統管理員。'
                line_bot_api.push_message(line_user.line_user_id, line_message)
            except:
                # 即使發送LINE通知失敗，也不影響密碼重設結果
                pass
            
            return Response({
                'success': True,
                'message': '密碼已成功重設'
            })
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': '找不到該用戶'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def _generate_reset_token(self, user):
        """生成重設密碼的臨時令牌"""
        import jwt
        from django.conf import settings
        
        # 令牌有效期為15分鐘
        payload = {
            'user_id': str(user.id),
            'exp': timezone.now() + timedelta(minutes=15)
        }
        
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
        return token
    
    def _validate_reset_token(self, token):
        """驗證重設密碼的臨時令牌"""
        import jwt
        from django.conf import settings
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            return payload['user_id']
        except:
            return None