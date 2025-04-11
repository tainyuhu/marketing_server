from decouple import config  # 確保正確導入

DEBUG = config('DJANGO_DEBUG'), # 是否開啟debug模式
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        'NAME': config('MYSQL_DATABASE'), # MySQL 資料庫的名稱
        'USER': config('MYSQL_USER'), # 使用者名稱
        'PASSWORD': config('MYSQL_PASSWORD'), # 密碼
        'HOST': config('DB_HOST', default='db'), # IP 地址
        'PORT': config('DB_PORT', default='3306'), # 埠號(mysql為 3306)
        "OPTIONS": {
            "sql_mode": "traditional",
            "charset": "utf8mb4"
        }
    }
}