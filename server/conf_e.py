# conf_e.py
import os
from dotenv import load_dotenv

# 強制重新加載
load_dotenv(override=True)

DEBUG = os.environ.get('DJANGO_DEBUG'), # 是否開啟debug模式
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        'NAME': os.environ.get('MYSQL_DATABASE'), # MySQL 資料庫的名稱
        'USER': os.environ.get('MYSQL_USER'), # 使用者名稱
        'PASSWORD': os.environ.get('MYSQL_PASSWORD'), # 密碼
        'HOST': os.environ.get('DB_HOST', default='db'), # IP 地址
        'PORT': os.environ.get('DB_PORT', default='3306'), # 埠號(mysql為 3306)
        "OPTIONS": {
            "sql_mode": "traditional",
            "charset": "utf8mb4"
        }
    }
}