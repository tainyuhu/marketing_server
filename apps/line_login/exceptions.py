# exceptions.py
from rest_framework.exceptions import APIException
from rest_framework import status
from django.utils.translation import gettext_lazy as _

class LineAccountNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _('未找到綁定的 LINE 帳號')
    default_code = "line_user_not_found"

class LineUnbindError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _('解除綁定時發生錯誤')
    default_code = "database_error"


class LineStateMissingException(APIException):
    """缺少 state 參數的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('缺少 state 參數')
    default_code = 'missing_state'

class LineStateInvalidException(APIException):
    """無效或過期的 state 參數異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('state 參數無效或已過期')
    default_code = 'invalid_state'

class LineAuthCodeMissingException(APIException):
    """缺少授權碼的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('未收到授權碼')
    default_code = 'authorization_code_missing'
    
class LineTokenExchangeException(APIException):
    """交換 token 失敗的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('與 LINE 平台交換令牌失敗')
    default_code = 'token_exchange_failed'

class LineUserDataMissingException(APIException):
    """無法獲取 LINE 用戶資料的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('無法獲取用戶資料')
    default_code = 'user_data_missing'


class LineStateMissingException(APIException):
    """缺少 state 參數的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('缺少 state 參數')
    default_code = 'missing_state'

class LineStateInvalidException(APIException):
    """無效或過期的 state 參數異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('state 參數無效或已過期')
    default_code = 'invalid_state'

class LineAuthCodeMissingException(APIException):
    """缺少授權碼的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('未收到授權碼')
    default_code = 'authorization_code_missing'
    
class LineTokenExchangeException(APIException):
    """交換 token 失敗的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('與 LINE 平台交換令牌失敗')
    default_code = 'token_exchange_failed'

class LineUserDataMissingException(APIException):
    """無法獲取 LINE 用戶資料的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('無法獲取用戶資料')
    default_code = 'user_data_missing'


class LineAccountAlreadyBindedException(APIException):
    """LINE 帳號已被綁定的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('此 LINE 帳號已綁定到其他用戶，請使用其他 LINE 帳號')
    default_code = 'line_account_already_binded'

class LineAccountNotFound(APIException):
    """未找到 LINE 帳號綁定的異常"""
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _('未找到 LINE 帳號綁定')
    default_code = 'line_account_not_found'

class LineUnbindError(APIException):
    """解除綁定時發生錯誤的異常"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _('解除綁定時發生錯誤')
    default_code = 'unbind_error'
    
class LineAccountNotBinded(APIException):
    """尚未綁定到系統中的異常"""
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _('尚未綁定到系統中，請先登入系統後進行綁定')
    default_code = 'line_account_not_binded'


class LineTemporaryTokenMissingException(APIException):
    """缺少臨時Token的異常"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('缺少臨時Token')
    default_code = 'temporary_token_missing'

class LineTemporaryTokenInvalidOrExpiredException(APIException):
    """無效或過期的臨時令牌"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('無效或過期的臨時令牌')
    default_code = 'temporary_token_invalid_or_expired'


class LineDatabaseException(APIException):
    """資料庫操作異常"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _('資料庫操作失敗')
    default_code = 'database_error'