from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import jwt
import requests
import json
from ..line_bot.models import LineUser
from django.contrib.auth import login
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from .exceptions import LineAccountNotFound, LineUnbindError
from rest_framework.exceptions import NotAuthenticated

class LineLoginService:
    """處理 LINE Login 相關的服務邏輯"""
    
    def __init__(self):
        self.token_url = "https://api.line.me/oauth2/v2.1/token" # 與 LINE 平台交換 token 的 URL
        self.profile_url = "https://api.line.me/v2/profile" # 獲取用戶信息的 URL
        
    def _get_auth_params(self, request):
        """統一獲取授權參數的邏輯"""
        if request.method == 'GET':
            return {
                'code': request.GET.get('code'), # 狀態碼
                'state': request.GET.get('state'), # 狀態
                'error': request.GET.get('error'), # 錯誤
                'error_description': request.GET.get('error_description') # 錯誤描述
            }
            
        try:
            if request.body:
                data = json.loads(request.body) # 嘗試從請求體獲取 JSON 數據
                return {
                    'code': data.get('code'), # 狀態碼
                    'state': data.get('state'), # 狀態
                    'error': data.get('error'), # 錯誤
                    'error_description': data.get('error_description') # 錯誤描述
                }
        except json.JSONDecodeError:
            pass
            
        return {
            'code': request.POST.get('code') or request.GET.get('code'),
            'state': request.POST.get('state') or request.GET.get('state'),
            'error': request.POST.get('error') or request.GET.get('error'),
            'error_description': (request.POST.get('error_description') or 
                                request.GET.get('error_description'))
        }

    def _exchange_token(self, code):
        """與 LINE 平台交換 token"""
        token_data = { # 請求參數
            'grant_type': 'authorization_code', # 授權類型
            'code': code, # 授權碼
            'redirect_uri': settings.LINE_LOGIN_CALLBACK_URL, # 重定向 URL
            'client_id': settings.LINE_LOGIN_CHANNEL_ID, # LINE Login Channel ID
            'client_secret': settings.LINE_LOGIN_CHANNEL_SECRET # LINE Login Channel Secret
        }

        try:
            # 發送請求，獲取 token
            response = requests.post(self.token_url, data=token_data)

            # 解析 JSON 數據
            token_json = response.json()
            
            # 檢查是否有錯誤
            if 'error' in token_json:
                return False, {
                    'error': token_json.get('error'),
                    'message': token_json.get('error_description', '獲取 Token 失敗')
                }
            
            return True, token_json
            
        except requests.RequestException as e:
            return False, {
                'error': 'request_error',
                'message': f'與 LINE 平台通信時發生錯誤: {str(e)}'
            }

    def _get_user_info_from_id_token(self, id_token):
        """從 ID Token 中解析用戶信息"""
        try:
            decoded = jwt.decode( # 解碼 ID Token (簡化版本，不進行完整驗證)
                id_token, 
                options={"verify_signature": False}
            )
            return {
                'id': decoded.get('sub'), # 用戶 ID
                'name': decoded.get('name'), # 用戶名稱
                'picture': decoded.get('picture'), # 用戶頭像
                'email': decoded.get('email') # 用戶郵箱
            }
        except Exception as e:
            print(f"ID Token 解析錯誤: {e}")
            return None

    def _get_user_info_from_api(self, access_token):
        """使用 API 獲取用戶信息"""
        try:
            # JWT 認證
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(self.profile_url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'id': data.get('userId'), # 用戶 ID
                    'name': data.get('displayName'), # 用戶名稱
                    'picture': data.get('pictureUrl'), # 用戶頭像
                    'status_message': data.get('statusMessage') # 用戶狀態消息
                }
        except requests.RequestException:
            return None
        
        return None
    
    def _get_user_info(self, token_data):
        """從 token 數據中獲取用戶信息
        嘗試從 ID Token 或 API 獲取
        """
        user_data = None
        
        # 嘗試從 ID Token 中獲取用戶信息
        if token_data.get('id_token'):
            user_data = self._get_user_info_from_id_token(token_data['id_token'])
        
        # 如果 ID Token 無效，則使用 API 獲取用戶信息
        if not user_data and token_data.get('access_token'):
            user_data = self._get_user_info_from_api(token_data['access_token'])
        
        return user_data
    
    def _update_line_user(self, line_user, user_data, token_data):
        """更新 LINE 用戶資料"""
        # 計算 token 過期時間
        expires_in = token_data.get('expires_in', 3600)
        token_expiry = timezone.now() + timedelta(seconds=expires_in)
        
        # 更新資料
        line_user.display_name = user_data.get('name')
        line_user.picture_url = user_data.get('picture')
        line_user.last_interaction = timezone.now()
        line_user.save()
        
        return line_user

    def save_line_user_data(self, user_data, token_data, request=None):
        """儲存或更新Line用戶的資料"""
        # 計算 token 過期時間
        # 更新或創建 LINE User
        line_user, created = LineUser.objects.update_or_create(
            line_user_id=user_data['id'],
            defaults={
                'user': request.user,
                'display_name': user_data.get('name'),
                'picture_url': user_data.get('picture'),
                'last_interaction': timezone.now(),
            }
        )

        return line_user, created

    def process_login(self, request):
        """處理登入流程的主要邏輯"""
        # 獲取授權參數
        auth_params = self._get_auth_params(request)
        
        # 檢查錯誤
        if auth_params.get('error'):
            return False, {
                'message': auth_params.get('error_description') or '登入時發生錯誤',
                'success': False,
                'error': auth_params['error'],
            }, status.HTTP_400_BAD_REQUEST
            
        # 檢查授權碼
        code = auth_params.get('code')
        if not code:
            return False, {
                'message': '未收到授權碼',
                'success': False,
                'error': 'authorization_code_missing',
            }, status.HTTP_400_BAD_REQUEST
            
        # 交換 token
        success, token_data = self._exchange_token(code)

        # 如果交換 token 失敗，返回錯誤
        if not success:
            return False, {
                'success': False,
                **token_data
            }, status.HTTP_400_BAD_REQUEST
            
        # 獲取用戶信息
        user_data = self._get_user_info(token_data)
        
        # 如果都還是無法獲取用戶信息，返回錯誤
        if not user_data or not user_data.get('id'):
            return False, {
                'message': '無法獲取用戶資料',
                'success': False,
                'error': 'user_data_missing',
            }, status.HTTP_400_BAD_REQUEST
        
        try:
            # 嘗試找到已綁定的用戶
            line_user = LineUser.objects.get(line_user_id=user_data['id'])
            
            # 更新 LINE 用戶的資料
            self._update_line_user(line_user, user_data, token_data)
            
            # 如果有關聯的 Django 用戶，執行登入
            if line_user.user:
                login(request, line_user.user)
            
            # 生成 JWT token
            access = AccessToken.for_user(line_user.user) # 生成訪問 token
            refresh = RefreshToken.for_user(line_user.user) # 生成刷新 token

            # 返回成功響應
            return True, {
                'success': True,
                'user': {
                    'id': line_user.user.id,
                    'username': line_user.user.username,
                    'line_user_id': line_user.user_id,
                    'display_name': line_user.display_name,
                    'picture_url': line_user.picture_url,
                    'is_new_user': False
                },
                'tokens': {
                    'access': str(access),
                    'refresh': str(refresh),
                    'expires_in': token_data.get('expires_in', 3600)
                }
            }, status.HTTP_200_OK
        
        except LineUser.DoesNotExist:
            # LINE 用戶未綁定，返回錯誤
            return False, {
                'message': '您的Line帳號尚未與系統綁定，請先登入系統進行帳號綁定。',
                'success': False,
                'error': 'line_account_not_binded',
                'line_user_id': user_data['id']
            }, status.HTTP_404_NOT_FOUND

        except Exception as e:
            return False, {
                'message': f'儲存用戶資料時發生錯誤: {str(e)}',
                'success': False,
                'error': 'database_error',
            }, status.HTTP_500_INTERNAL_SERVER_ERROR


    def bind_account(self, request):
        """將 LINE 帳號綁定到當前用戶"""
        # 獲取授權參數
        auth_params = self._get_auth_params(request)
        # 檢查錯誤
        if auth_params.get('error'):
            return False, {
                'message': auth_params.get('error_description') or '綁定時發生錯誤',
                'success': False,
                'error': auth_params['error'],
            }, status.HTTP_400_BAD_REQUEST
            
        # 檢查授權碼
        code = auth_params.get('code')
        if not code:
            return False, {
                'message': '未收到授權碼',
                'success': False,
                'error': 'authorization_code_missing',
            }, status.HTTP_400_BAD_REQUEST
            
        # 交換 token
        success, token_data = self._exchange_token(code)
        if not success:
            return False, {
                'success': False,
                **token_data # 包含error、message
            }, status.HTTP_400_BAD_REQUEST

        
        # 獲取用戶信息
        user_data = self._get_user_info(token_data)

        # 如果都還是無法獲取用戶信息，返回錯誤
        if not user_data or not user_data.get('id'):
            return False, {
                'message': '無法獲取用戶資料',
                'success': False,
                'error': 'user_data_missing',
            }, status.HTTP_400_BAD_REQUEST
        try:
            # 檢查 LINE 帳號是否已被其他用戶綁定
            existing_line_user = LineUser.objects.filter(line_user_id=user_data['id']).first()
            if existing_line_user and existing_line_user.user_id != request.user.id:
                return False, {
                    'message': '此 LINE 帳號已經被綁定到其他用戶',
                    'success': False,
                    'error': 'line_account_already_binded',
                }, status.HTTP_400_BAD_REQUEST

            # 儲存用戶資料
            line_user, created = self.save_line_user_data(user_data, token_data, request)

            return True, {
                'message': '成功綁定 LINE 帳號',
                'success': True,
                'user': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'line_user_id': line_user.line_user_id,
                    'display_name': line_user.display_name,
                    'picture_url': line_user.picture_url,
                    'is_new_binding': created
                }
            }, status.HTTP_200_OK
          
        except Exception as e:
            return False, {
                'message': f'綁定 LINE 帳號時發生錯誤: {str(e)}',
                'success': False,
                'error': 'database_error',
            }, status.HTTP_500_INTERNAL_SERVER_ERROR


    def unbind_account(self, request):
        """解除 LINE 帳號綁定"""
        user = request.user # 取得當前用戶

        # 檢查是否已登入
        # 如果用戶未登入，返回錯誤
        if not user.is_authenticated:
            raise NotAuthenticated("需要登入才能解除綁定")

        try:
            # 嘗試刪除用戶的 LINE 綁定
            line_user = LineUser.objects.get(user=user)
            line_user.delete()

            # 直接返回成功訊息，不再返回狀態碼
            return {
                'message': 'LINE 帳號已成功解除綁定',
                'success': True,
            }
        
        # 如果用戶未綁定 LINE 帳號，返回錯誤
        except LineUser.DoesNotExist:
            raise LineAccountNotFound()
        
        # 如果刪除時發生錯誤，返回錯誤
        except Exception as e:
            raise LineUnbindError(detail=f"解除綁定時發生錯誤: {str(e)}")