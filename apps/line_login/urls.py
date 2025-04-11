# urls.py
from django.urls import path
from .views import (
    get_line_login_url, 
    line_login_callback, 
    exchange_temp_token,
    unbind_account,
)

urlpatterns = [
    # LINE Login 相關 API
    path('url/', get_line_login_url, name='get_line_login_url'),
    path('callback/', line_login_callback, name='line_login_callback'),
    path('exchange-temp-token/', exchange_temp_token, name='exchange_temp_token'),
    path('unbind-account/', unbind_account, name='unbind_account'),
]