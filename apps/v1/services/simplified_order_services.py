"""
訂單編號生成服務
提供訂單編號生成的邏輯
"""
import random
import string
from django.utils import timezone
from apps.v1.models import Order

def generate_order_number():
    """
    生成唯一的訂單編號
    格式: ORD-YYYYMMDD-NNNNN-ZZZ
    YYYYMMDD: 年月日
    NNNNN: 5位隨機數字
    ZZZ: 隨機字元
    
    返回:
        str: 生成的訂單編號
    """
    # 年月日部分
    date_part = timezone.now().strftime('%Y%m%d')
    
    # 5位隨機數字
    random_digits = ''.join(random.choices('0123456789', k=5))
    
    # 隨機字元，使用數字和大寫字母，排除容易混淆的字符
    random_chars = ''.join(random.choices(
        string.ascii_uppercase.replace('O', '').replace('I', '') + 
        string.digits.replace('0', '').replace('1', ''),
        k=3
    ))
    
    # 組合訂單編號
    order_number = f"ORD-{date_part}-{random_digits}-{random_chars}"
    
    # 檢查是否已存在相同的訂單編號，如果存在則重新生成
    while Order.objects.filter(order_number=order_number).exists():
        random_digits = ''.join(random.choices('0123456789', k=5))
        random_chars = ''.join(random.choices(
            string.ascii_uppercase.replace('O', '').replace('I', '') + 
            string.digits.replace('0', '').replace('1', ''),
            k=3
        ))
        order_number = f"ORD-{date_part}-{random_digits}-{random_chars}"
    
    return order_number