# views.py
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils import timezone
import os
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from urllib.parse import urlencode
import json
import traceback
import uuid
from apps.system.models import User
from .line_services import LineLoginService


class LineAuthParams:
    """管理 Line 登入參數的類別"""
    
    def __init__(self, mode='login', user_id=None):
        self.state = str(uuid.uuid4()) # CSRF protection
        self.nonce = str(uuid.uuid4()) # Anti-replay protection
        self.mode = mode # login or binding
        self.user_id = user_id # User ID for binding mode
        self.temp_token = None # Temporary token for frontend redirect
    
    # 將狀態和參數存儲在緩存中
    def store_in_cache(self, timeout=600):
        """Store state and parameters in cache"""
        cache_key = f"line_state_{self.state}"
        cache_data = {
            'state': self.state,
            'mode': self.mode,
            'user_id': self.user_id
        }
        cache.set(cache_key, json.dumps(cache_data), timeout)
    
    # 生成 Line 登入 URL
    def generate_login_url(self):
        """Generate LINE login URL with required parameters"""
        params = {
            'response_type': 'code',
            'client_id': settings.LINE_LOGIN_CHANNEL_ID,
            'redirect_uri': settings.LINE_LOGIN_CALLBACK_URL,
            'state': self.state,
            'scope': 'profile openid email',
            'nonce': self.nonce
        }
        auth_url = 'https://access.line.me/oauth2/v2.1/authorize'
        return f"{auth_url}?{urlencode(params)}"
    

    # 從狀態中檢索參數
    @classmethod
    def from_state(cls, state):
        """Retrieve params from cache using state"""
        cache_key = f"line_state_{state}"
        cached_data_json = cache.get(cache_key)
        
        if not cached_data_json:
            return None
            
        cached_data = json.loads(cached_data_json)
        auth_params = cls(
            mode=cached_data.get('mode', 'login'),
            user_id=cached_data.get('user_id', None)
        )
        auth_params.state = cached_data.get('state')
        
        # Delete after retrieving (one-time use)
        cache.delete(cache_key)
        
        return auth_params
    
    # 生成臨時令牌
    def generate_temp_token(self):
        """Generate a temporary token for frontend redirect"""
        self.temp_token = str(uuid.uuid4())
        return self.temp_token

class AuthResultHandler:
    """處理 Line 登入結果的類別"""
    
    def __init__(self, frontend_url):
        self.frontend_url = frontend_url # Frontend URL for redirect
        self.success = False # Success flag
        self.data = {} # Response data
        self.status_code = status.HTTP_400_BAD_REQUEST # Default status code
        self.mode = 'login' # Default mode (login or binding)
        self.temp_token = None # Temporary token for frontend redirect
    
    def set_error(self, error, message, status_code=status.HTTP_400_BAD_REQUEST):
        """設置錯誤信息"""
        self.success = False
        self.data = {
            'message': message,
            'success': False,
            'error': error,
            'status_code': status_code,
            'mode': self.mode  # 儲存模式資訊
        }
        self.status_code = status_code
        return self
    
    def set_success(self, data, status_code=status.HTTP_200_OK):
        """設置成功訊息"""
        self.success = True
        self.data = data
        self.status_code = status_code
        return self
    
    def set_mode(self, mode):
        """設置身份驗證模式 (login 或 binding)"""
        self.mode = mode
        return self
    
    def store_result(self, temp_token, timeout=300):
        """將結果存儲在緩存中"""
        # 如果未提供臨時令牌，則生成一個
        if not temp_token:
            temp_token = str(uuid.uuid4())
        
        # 保存臨時令牌以便後續使用
        self.temp_token = temp_token
        
        # 確保數據中包含成功/失敗標記和模式
        if isinstance(self.data, dict):
            if 'success' not in self.data:
                self.data['success'] = self.success
            if 'mode' not in self.data:
                self.data['mode'] = self.mode

        cache.set(
            f"temp_auth_{temp_token}",
            self.data,
            timeout=timeout
        )
        return self
    
    def get_redirect_url(self):
        """建立重定向 URL"""
        # 所有情況都使用相同的 URL 結構，只傳遞 temp_token
        if not self.temp_token:
            # 首先確保生成臨時令牌並保存結果
            self.store_result()
        
        # Normal case with temp token
        return f"{self.frontend_url}?temp_token={self.temp_token}&mode={self.mode}"


@api_view(['GET'])
@permission_classes([AllowAny])
def get_line_login_url(request):
    """
    獲取 LINE Login URL
    """
    # 獲取模式參數 (login 或 binding)
    mode = request.GET.get('mode', 'login')

    # 確認在綁定模式下用戶必須已登入
    if mode == 'binding' and not request.user.is_authenticated:
        return Response({
            'message': '必須登入才能綁定 LINE 帳號',
            'success': False,
            'error': 'auth_required',
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # 建立類別實例並存儲在緩存中
    auth_params = LineAuthParams(
        mode=mode,
        user_id=str(request.user.id) if request.user and request.user.is_authenticated else None
    )
    auth_params.store_in_cache()
    
    # 回傳 LINE Login URL
    line_login_url = auth_params.generate_login_url()
    return Response({'login_url': line_login_url})



@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def line_login_callback(request):
    """
    處理 LINE Login 的授權碼
    前端從 URL 獲取授權碼後調用此 API
    """
    # 檢查請求方法
    if request.method not in ['GET', 'POST']:
        return Response({
            'message': f'不支持的方法: {request.method}',
            'success': False,
            'error': 'method_not_allowed',
        }, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    # 獲取前端 URL (.env 中設定)
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:8000')

    # 建立結果處理器類別
    result_handler = AuthResultHandler(FRONTEND_URL)
    
    try:
        # 驗證 state參數以防止 CSRF 攻擊
        received_state = request.GET.get('state')
        if not received_state:
            print("LINE 回調 - 錯誤: 缺少 state 參數")
            return result_handler.set_error(
                message='缺少 state 參數',
                error='missing_state', 
                status_code=status.HTTP_400_BAD_REQUEST
            ).get_redirect_url()
        
        # Retrieve stored parameters
        auth_params = LineAuthParams.from_state(received_state)
        if not auth_params:
            print("LINE 回調 - 錯誤: state 參數無效或已過期")
            return result_handler.set_error(
                message='state 參數無效或已過期',
                error='invalid_state', 
                status_code=status.HTTP_400_BAD_REQUEST
            ).get_redirect_url()
            
        # 檢查 state 參數是否匹配
        if received_state != auth_params.state:
            print("LINE 回調 - 錯誤: state 參數不匹配")
            return result_handler.set_error(
                message='state 參數不匹配',
                error='invalid_state', 
                status_code=status.HTTP_400_BAD_REQUEST
            ).get_redirect_url()
        
        # Create LINE service instance
        service = LineLoginService()
        result_handler.set_mode(auth_params.mode)
        
        # Generate temporary token for response
        temp_token = auth_params.generate_temp_token()
        
       # 處理綁定模式
        if auth_params.mode == 'binding':
            return handle_binding_mode(
                request, 
                auth_params.user_id, 
                service, 
                temp_token,
                result_handler
            )
        # 處理登入模式
        else:  # login mode
            return handle_login_mode(
                request, 
                service, 
                temp_token,
                result_handler
            )
            
    except Exception as e:
        # 記錄錯誤
        error_traceback = traceback.format_exc()
        print(f"LINE 登入錯誤: {error_traceback}")
        
        # 為未預期錯誤創建一個臨時令牌
        temp_token = str(uuid.uuid4())
        
        # 保存錯誤信息到緩存
        error_data = {
            'message': str(e),
            'success': False,
            'error': 'unexpected_error',
            'mode': request.GET.get('mode', 'login'),  # 嘗試保留模式
            'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR
        }
        
        cache.set(
            f"temp_auth_{temp_token}",
            error_data,
            timeout=300  # 5分鐘過期
        )
        
        # 使用簡化的重定向 URL
        error_redirect_url = f"{FRONTEND_URL}/auth/line-callback?temp_token={temp_token}"
        return redirect(error_redirect_url)


def handle_binding_mode(request, user_id, service, temp_token, result_handler):
    """處理 LINE 帳號綁定模式的邏輯"""
    # 檢查是否提供了用戶ID
    if not user_id:
        print("LINE 回調 - 錯誤: 綁定模式下缺少用戶ID")
        result_handler.set_error(
            message='無法識別用戶身份，請重新登入後再嘗試綁定',
            error='missing_user_id',
            status_code=status.HTTP_400_BAD_REQUEST
        )
        return redirect(result_handler.get_redirect_url())
            
    try:
        # 嘗試獲取用戶
        user = User.objects.get(id=user_id)
        # 手動設置 request.user，以便 bind_account 可以正確識別用戶
        request.user = user
        
        # 處理綁定
        success, response_data, status_code = service.bind_account(request)
        
        # 檢查綁定結果
        if not success:
            result_handler.set_error(
                error=response_data.get('error', 'binding_failed'),
                message=response_data.get('message', '綁定失敗'),
                status_code=status_code
            )
        else:
            result_handler.set_success(
                data=response_data, 
                status_code=status_code
            )
        
        result_handler.store_result(temp_token)
        
        # Redirect to frontend
        return redirect(result_handler.get_redirect_url())
            
    except User.DoesNotExist:
        print(f"LINE 回調 - 錯誤: 找不到用戶 ID {user_id}")
        result_handler.set_error(
            'user_not_found',
            '找不到對應的用戶，請重新登入後再嘗試綁定',
            status.HTTP_404_NOT_FOUND
        )
        return redirect(result_handler.get_redirect_url())


def handle_login_mode(request, service, temp_token, result_handler):
    """處理 LINE 登入模式的邏輯"""
    # Process login
    success, response_data, status_code = service.process_login(request)
    
    # 登入失敗
    if not success:
        result_handler.set_error(
            error=response_data.get('error', 'login_failed'),
            message=response_data.get('message', '登入失敗'),
            status_code=status_code
        )
    else:
        # Format successful login data
        result_data = {
            'success': True,
            'access_token': response_data['tokens']['access'],
            'refresh_token': response_data['tokens']['refresh'],
            'user_id': response_data['user']['id'],
            'line_user_id': response_data['user']['line_user_id'],
            'display_name': response_data['user']['display_name'],
            'picture_url': response_data['user']['picture_url'],
            'username': response_data['user']['username'],
            'status_code': status_code
        }
        result_handler.set_success(
            data=result_data, 
            status_code=status_code
        )
    
    # Store result and redirect
    result_handler.store_result(temp_token)
    return redirect(result_handler.get_redirect_url())



@api_view(['POST'])
@permission_classes([AllowAny])
def exchange_temp_token(request):
    """透過取得的臨時令牌交換實際的緩存資料"""
    # Read temporary token
    temp_token = request.data.get('temp_token')
    
    # 如果沒有提供臨時令牌，返回錯誤
    if not temp_token:
        return Response({
            'message': '請提供臨時令牌',
            'error': 'temporary_token_missing',
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # 從緩存獲取存儲的令牌和用戶數據
    cache_key = f"temp_auth_{temp_token}"
    auth_data = cache.get(cache_key)

    if not auth_data:
        return Response({
            'message': '無效或過期的臨時令牌',
            'error': 'temporary_token_invalid_or_expired',
        }, status=status.HTTP_400_BAD_REQUEST)

    # 使用完即刪除，確保一次性使用
    cache.delete(cache_key)
    
    # 返回實際令牌和用戶數據
    return Response(
        auth_data, 
        status=auth_data.get('status_code', status.HTTP_200_OK)
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unbind_account(request):
    """解除 LINE 帳號綁定"""
    try:
        service = LineLoginService()
        response_data = service.unbind_account(request)
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        # 任何未捕獲的例外都會由你的 exception_handler 處理
        raise e