from django.core.management.base import BaseCommand
from apps.v1.models import ActivityProduct

class Command(BaseCommand):
    help = "更新所有活動商品的庫存"

    def handle(self, *args, **kwargs):
        self.stdout.write("🔄 計算並更新活動商品庫存...")
        
        # 取得所有活動商品
        activity_products = ActivityProduct.objects.all()
        updated_count = 0
        
        for ap in activity_products:
            # 計算可用庫存
            calculated_stock = ap.calculate_available_stock()
            
            # 更新庫存值
            if ap.stock != calculated_stock:
                old_stock = ap.stock
                ActivityProduct.objects.filter(id=ap.id).update(stock=calculated_stock)
                updated_count += 1
                self.stdout.write(f"商品: {ap.product.product_name} - 舊庫存: {old_stock}, 新庫存: {calculated_stock}")
        
        self.stdout.write(self.style.SUCCESS(f"✅ 已更新 {updated_count} 個活動商品的庫存"))