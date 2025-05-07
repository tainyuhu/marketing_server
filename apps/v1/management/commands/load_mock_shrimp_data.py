from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import IntegrityError, transaction, connection
from apps.v1.models import (
    Item, Batch, Product, ProductItemRelation,
    ProductDefaultPrice, Activity, ActivityProduct,
    PromotionRule, Cart, CartItem, PromotionRuleRelation
)

class Command(BaseCommand):
    help = "載入白蝦測試資料（品號、批號、商品、促銷、購物車）"

    def handle(self, *args, **kwargs):
        self.stdout.write("🧹 清除所有現有資料...")
        
        # 使用SQL直接刪除資料 (繞過軟刪除機制)
        try:
            with connection.cursor() as cursor:
                # 先關閉外鍵約束檢查
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                
                # 清空購物車相關表
                self.stdout.write("- 清空購物車相關表")
                cursor.execute("DELETE FROM v1_wms_cart_item;")
                cursor.execute("DELETE FROM v1_wms_cart;")
                
                # 清空促銷規則相關表
                self.stdout.write("- 清空促銷規則相關表")
                cursor.execute("DELETE FROM v1_wms_promotion_rule_relation;")
                cursor.execute("DELETE FROM v1_wms_promotion_rule;")
                
                # 一一刪除每個表的數據
                self.stdout.write("- 清空 v1_wms_activity_product 表")
                cursor.execute("DELETE FROM v1_wms_activity_product;")
                
                self.stdout.write("- 清空 v1_wms_product_item_relation 表")
                cursor.execute("DELETE FROM v1_wms_product_item_relation;")
                
                self.stdout.write("- 清空 v1_wms_product_default_price 表")
                cursor.execute("DELETE FROM v1_wms_product_default_price;")
                
                self.stdout.write("- 清空 v1_wms_activity 表")
                cursor.execute("DELETE FROM v1_wms_activity;")
                
                self.stdout.write("- 清空 v1_wms_product 表")
                cursor.execute("DELETE FROM v1_wms_product;")
                
                self.stdout.write("- 清空 v1_wms_batch 表")
                cursor.execute("DELETE FROM v1_wms_batch;")
                
                self.stdout.write("- 清空 v1_wms_item 表")
                cursor.execute("DELETE FROM v1_wms_item;")
                
                # 重新啟用外鍵約束檢查
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
                
                self.stdout.write(self.style.SUCCESS("🗑️ 所有資料已使用SQL直接清除完畢!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"清除資料時發生錯誤: {e}"))
            return  # 如果清除出錯則停止執行

        self.stdout.write("🦐 建立品號與批號...")
        items = []
        for data in [
            ("SHRIMP-A", "白蝦A", "500g/盒", 20, "常態商品A"),
            ("SHRIMP-B", "白蝦B", "1kg/盒", 10, "常態商品B，買一送一"),
            ("SHRIMP-C", "白蝦C", "250g/盒", 30, "活動商品C"),
            ("SHRIMP-D", "白蝦D", "250g/盒", 30, "活動商品D"),
            ("SHRIMP-E", "白蝦E", "250g/盒", 30, "活動商品E"),
            ("SHRIMP-F", "白蝦F", "300g/盒", 25, "活動商品F，買五送二"),
            ("SHRIMP-G", "白蝦G", "400g/盒", 20, "活動商品G，買四送一"),
        ]:
            try:
                # 先檢查是否已存在
                item, created = Item.objects.get_or_create(
                    item_code=data[0],
                    defaults={
                        "name": data[1],
                        "specification": data[2],
                        "unit": "盒",
                        "box_size": data[3],
                        "status": True,
                        "remark": data[4]
                    }
                )
                if not created:
                    self.stdout.write(self.style.WARNING(f"品號 {data[0]} 已存在，跳過建立"))
                items.append(item)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"建立品號 {data[0]} 時發生錯誤: {e}"))
                continue

        today = timezone.now().date()
        batches = []
        for i, batch_data in enumerate([
            ("A-BATCH-001", "主倉", "A1", 100, 80, 20, 5),
            ("B-BATCH-001", "主倉", "A2", 200, 150, 50, 10),
            ("C-BATCH-001", "主倉", "B1", 150, 100, 50, 10),
            ("D-BATCH-001", "主倉", "B2", 120, 100, 20, 8),
            ("E-BATCH-001", "主倉", "B3", 130, 110, 20, 9),
            ("F-BATCH-001", "主倉", "C1", 140, 120, 20, 6),
            ("G-BATCH-001", "主倉", "C2", 160, 130, 30, 8),
        ]):
            if i >= len(items):
                self.stdout.write(self.style.ERROR(f"沒有足夠的品號來建立批號 {batch_data[0]}"))
                continue
                
            try:
                batch, created = Batch.objects.get_or_create(
                    batch_number=batch_data[0],
                    defaults={
                        "item": items[i],
                        "warehouse": batch_data[1],
                        "location": batch_data[2],
                        "quantity": batch_data[3],
                        "active_stock": batch_data[4],
                        "stock": batch_data[5],
                        "box_count": batch_data[6],
                        "expiry_date": today + timedelta(days=30)
                    }
                )
                if not created:
                    self.stdout.write(self.style.WARNING(f"批號 {batch_data[0]} 已存在，跳過建立"))
                batches.append(batch)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"建立批號 {batch_data[0]} 時發生錯誤: {e}"))
                continue

        self.stdout.write("📦 建立產品與價格...")
        products = []
        for data in [
            ("PROD-A", "白蝦A商品", "常態", False, "常態商品A說明"),
            ("PROD-B", "白蝦B商品", "常態", True, "常態商品B說明，買一送一"),
            ("PROD-C", "白蝦C商品", "活動", True, "活動商品C說明，買三送一"),
            ("PROD-D", "白蝦D商品", "活動", True, "活動商品D說明，買三送一"),
            ("PROD-E", "白蝦E商品", "活動", True, "活動商品E說明，買三送一"),
            ("PROD-F", "白蝦F商品", "活動", True, "活動商品F說明，買五送二"),
            ("PROD-G", "白蝦G商品", "活動", True, "活動商品G說明，買四送一"),
        ]:
            try:
                # 建立產品時添加圖片網址
                product, created = Product.objects.get_or_create(
                    product_code=data[0],
                    defaults={
                        "product_name": data[1],
                        "product_category": data[2],
                        "is_promotion": data[3],
                        "description": data[4],
                        "main_image_url": "http://3.27.170.92/uploads/pexels-amar-29320542.jpg"  # 添加主圖網址
                    }
                )
                if not created:
                    self.stdout.write(self.style.WARNING(f"產品 {data[0]} 已存在，跳過建立"))
                products.append(product)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"建立產品 {data[0]} 時發生錯誤: {e}"))
                continue

        # 根據需求，只有 PROD-A 進入 ProductDefaultPrice 表
        try:
            ProductDefaultPrice.objects.get_or_create(
                product=products[0],  # PROD-A
                defaults={"price": 300.00, "stock": 100}
            )
            self.stdout.write(self.style.SUCCESS(f"✅ 已為 {products[0].product_code} 建立常態價格"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"建立產品價格時發生錯誤: {e}"))

        self.stdout.write("🔗 建立產品與批號的關聯...")
        min_length = min(len(products), len(items), len(batches))
        for i in range(min_length):
            try:
                ProductItemRelation.objects.get_or_create(
                    product=products[i],
                    batch=batches[i],
                    defaults={
                        "item": items[i],
                        "quantity": 1,
                        "unit": "盒"
                    }
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"建立產品與批號關聯時發生錯誤: {e}"))
                continue

        self.stdout.write("🎉 建立活動與商品優惠...")
        try:
            # 活動起訖日期
            start_date = timezone.now()
            end_date = timezone.now() + timedelta(days=30)
            
            # 建立活動時添加網址和HTML內容
            activity1, _ = Activity.objects.get_or_create(
                name="白蝦三入送一活動",
                defaults={
                    "description": "針對商品C~E買三送一",
                    "start_date": start_date,
                    "end_date": end_date,
                    "activity_type": "product_promotion",
                    "banner_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "image_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "detail_html": "<p>本活動為限時促銷，凡購買指定商品即可享有專屬優惠。</p><ul><li>商品優惠包含買贈、折扣或免運。</li><li>商品數量有限，售完為止。</li><li>圖片僅供參考，商品以實物為準。</li></ul><p>請加入購物車後至結帳頁面確認最終價格與贈品內容。</p>",
                    "rules_html": "<ol><li>活動期間：自 {{startDate}} 起至 {{endDate}} 止。</li><li>本活動僅適用於指定商品，非指定商品不在優惠範圍內。</li><li>若訂單取消或退貨，系統將自動取消優惠內容。</li><li>若活動包含贈品，贈品不得更換、兌換現金或折抵。</li><li>本公司保留隨時修改、變更、取消活動內容之權利。</li></ol>"
                }
            )

            activity2, _ = Activity.objects.get_or_create(
                name="全館滿額折扣",
                defaults={
                    "description": "滿2000折100",
                    "start_date": start_date,
                    "end_date": end_date,
                    "activity_type": "sitewide_discount",
                    "banner_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "image_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "detail_html": "<p>本活動為限時促銷，凡購買指定商品即可享有專屬優惠。</p><ul><li>商品優惠包含買贈、折扣或免運。</li><li>商品數量有限，售完為止。</li><li>圖片僅供參考，商品以實物為準。</li></ul><p>請加入購物車後至結帳頁面確認最終價格與贈品內容。</p>",
                    "rules_html": "<ol><li>活動期間：自 {{startDate}} 起至 {{endDate}} 止。</li><li>本活動僅適用於指定商品，非指定商品不在優惠範圍內。</li><li>若訂單取消或退貨，系統將自動取消優惠內容。</li><li>若活動包含贈品，贈品不得更換、兌換現金或折抵。</li><li>本公司保留隨時修改、變更、取消活動內容之權利。</li></ol>"
                }
            )
            
            activity3, _ = Activity.objects.get_or_create(
                name="商品B買一送一",
                defaults={
                    "description": "買一送一活動",
                    "start_date": start_date,
                    "end_date": end_date,
                    "activity_type": "internal_promotion",
                    "banner_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "image_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "detail_html": "<p>本活動為限時促銷，凡購買指定商品即可享有專屬優惠。</p><ul><li>商品優惠包含買贈、折扣或免運。</li><li>商品數量有限，售完為止。</li><li>圖片僅供參考，商品以實物為準。</li></ul><p>請加入購物車後至結帳頁面確認最終價格與贈品內容。</p>",
                    "rules_html": "<ol><li>活動期間：自 {{startDate}} 起至 {{endDate}} 止。</li><li>本活動僅適用於指定商品，非指定商品不在優惠範圍內。</li><li>若訂單取消或退貨，系統將自動取消優惠內容。</li><li>若活動包含贈品，贈品不得更換、兌換現金或折抵。</li><li>本公司保留隨時修改、變更、取消活動內容之權利。</li></ol>"
                }
            )
            
            activity4, _ = Activity.objects.get_or_create(
                name="商品F和G特別促銷",
                defaults={
                    "description": "商品F買五送二，商品G買四送一活動",
                    "start_date": start_date,
                    "end_date": end_date,
                    "activity_type": "product_promotion",
                    "banner_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "image_url": "http://3.27.170.92/uploads/fried-shrimps-with-herbs-close-up-view.jpg",
                    "detail_html": "<p>本活動為限時促銷，凡購買指定商品即可享有專屬優惠。</p><ul><li>商品優惠包含買贈、折扣或免運。</li><li>商品數量有限，售完為止。</li><li>圖片僅供參考，商品以實物為準。</li></ul><p>請加入購物車後至結帳頁面確認最終價格與贈品內容。</p>",
                    "rules_html": "<ol><li>活動期間：自 {{startDate}} 起至 {{endDate}} 止。</li><li>本活動僅適用於指定商品，非指定商品不在優惠範圍內。</li><li>若訂單取消或退貨，系統將自動取消優惠內容。</li><li>若活動包含贈品，贈品不得更換、兌換現金或折抵。</li><li>本公司保留隨時修改、變更、取消活動內容之權利。</li></ol>"
                }
            )

            # 建立活動商品關聯 (ActivityProduct)，不再包含優惠邏輯
            # 商品 C, D, E 的買三送一活動
            activity_products = []
            for product_index in [2, 3, 4]:  # 商品C, D, E
                if product_index < len(products):
                    ap, _ = ActivityProduct.objects.get_or_create(
                        activity=activity1,
                        product=products[product_index],
                        defaults={
                            "price": 280.00,
                            "original_price": 300.00,
                            "stock": 0  # 初始設為0，後續會更新
                        }
                    )
                    activity_products.append(ap)
            
            # 商品B (買一送一) - 活動商品
            ap_b, _ = ActivityProduct.objects.get_or_create(
                activity=activity3,
                product=products[1],  # 商品B
                defaults={
                    "price": 500.00,
                    "original_price": 500.00,
                    "stock": 0  # 初始設為0，後續會更新
                }
            )
            activity_products.append(ap_b)
            
            # 商品F (買五送二) - 活動商品
            ap_f, _ = ActivityProduct.objects.get_or_create(
                activity=activity4,
                product=products[5],  # 商品F
                defaults={
                    "price": 380.00,
                    "original_price": 400.00,
                    "stock": 0  # 初始設為0，後續會更新
                }
            )
            activity_products.append(ap_f)
            
            # 商品G (買四送一) - 活動商品
            ap_g, _ = ActivityProduct.objects.get_or_create(
                activity=activity4,
                product=products[6],  # 商品G
                defaults={
                    "price": 430.00,
                    "original_price": 450.00,
                    "stock": 0  # 初始設為0，後續會更新
                }
            )
            activity_products.append(ap_g)
            
            self.stdout.write(self.style.SUCCESS(f"✅ 已建立 {len(activity_products)} 個活動商品"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"建立活動與優惠時發生錯誤: {e}"))

        # 更新所有活動商品的庫存計算
        self.stdout.write("🔄 計算並更新活動商品庫存...")
        try:
            # 取得所有活動商品
            activity_products = ActivityProduct.objects.all()
            updated_count = 0
            
            for ap in activity_products:
                # 計算可用庫存
                calculated_stock = ap.calculate_available_stock()
                
                # 更新庫存值
                if ap.stock != calculated_stock:
                    ActivityProduct.objects.filter(id=ap.id).update(stock=calculated_stock)
                    updated_count += 1
                    
            self.stdout.write(self.style.SUCCESS(f"✅ 已更新 {updated_count} 個活動商品的庫存"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"更新活動商品庫存時發生錯誤: {e}"))

        # 建立促銷規則
        self.stdout.write("📏 建立促銷規則...")
        
        try:
            # 獲取之前建立的活動，以防變數未正確傳遞
            activity1 = Activity.objects.get(name="白蝦三入送一活動")
            activity2 = Activity.objects.get(name="全館滿額折扣")
            activity3 = Activity.objects.get(name="商品B買一送一")
            activity4 = Activity.objects.get(name="商品F和G特別促銷")
            
            # 獲取活動商品，以防變數未正確傳遞
            ap_f = ActivityProduct.objects.get(activity=activity4, product__product_code="PROD-F")
            ap_g = ActivityProduct.objects.get(activity=activity4, product__product_code="PROD-G")
            
            # 1. 白蝦三入送一活動 - 針對商品C~E (綁定 Activity ID)
            # 買三送一規則
            buy3_get1_rule, _ = PromotionRule.objects.get_or_create(
                name="白蝦買3送1優惠",
                defaults={
                    "description": "買3送1優惠",
                    "rule_type": "buy_gift",
                    "threshold_quantity": 3,
                    "discount_amount": None,
                    "is_stackable": False,
                    "is_gift_same_product": True,  # 贈品是同商品
                    "gift_quantity": 1  # 贈送1件
                }
            )
            
            # 建立與Activity的關聯 (三入送一活動的規則綁定到活動)
            PromotionRuleRelation.objects.get_or_create(
                promotion_rule=buy3_get1_rule,
                activity=activity1,  # 綁定到活動1
                defaults={
                    "is_active": True,
                    "priority": 10
                }
            )
            
            # 2. 商品B買一送一 (綁定 Product ID)
            buy1_get1_rule, _ = PromotionRule.objects.get_or_create(
                name="白蝦B買1送1優惠",
                defaults={
                    "description": "商品B買1送1",
                    "rule_type": "buy_gift",
                    "threshold_quantity": 1,
                    "discount_amount": None,
                    "is_stackable": False,
                    "is_gift_same_product": True,  # 贈品是同商品
                    "gift_quantity": 1  # 贈送1件
                }
            )
            
            # 將規則關聯到商品B
            PromotionRuleRelation.objects.get_or_create(
                promotion_rule=buy1_get1_rule,
                product=products[1],  # 綁定到商品B
                defaults={
                    "is_active": True,
                    "priority": 10
                }
            )
            
            # 3. 商品F買五送二 (綁定 ActivityProduct ID)
            buy5_get2_rule, _ = PromotionRule.objects.get_or_create(
                name="白蝦F買5送2優惠",
                defaults={
                    "description": "商品F買5送2",
                    "rule_type": "buy_gift",
                    "threshold_quantity": 5,
                    "discount_amount": None,
                    "is_stackable": False,
                    "is_gift_same_product": True,  # 贈品是同商品
                    "gift_quantity": 2  # 贈送2件
                }
            )
            
            # 將規則關聯到活動商品F
            PromotionRuleRelation.objects.get_or_create(
                promotion_rule=buy5_get2_rule,
                activity_product=ap_f,  # 綁定到活動商品F
                defaults={
                    "is_active": True,
                    "priority": 10
                }
            )
            
            # 4. 商品G買四送一 (綁定 ActivityProduct ID)
            buy4_get1_rule, _ = PromotionRule.objects.get_or_create(
                name="白蝦G買4送1優惠",
                defaults={
                    "description": "商品G買4送1",
                    "rule_type": "buy_gift",
                    "threshold_quantity": 4,
                    "discount_amount": None,
                    "is_stackable": False,
                    "is_gift_same_product": True,  # 贈品是同商品
                    "gift_quantity": 1  # 贈送1件
                }
            )
            
            # 將規則關聯到活動商品G
            PromotionRuleRelation.objects.get_or_create(
                promotion_rule=buy4_get1_rule,
                activity_product=ap_g,  # 綁定到活動商品G
                defaults={
                    "is_active": True,
                    "priority": 10
                }
            )
            
            # 5. 全館滿額折扣 - 滿2000折100
            site_discount_rule, _ = PromotionRule.objects.get_or_create(
                name="全館滿2000折100",
                defaults={
                    "description": "訂單滿2000元折抵100元",
                    "rule_type": "order_discount",
                    "threshold_amount": 2000.00,
                    "discount_amount": 100.00,
                    "is_stackable": False
                }
            )
            
            # 將全館折扣規則設為全站適用
            PromotionRuleRelation.objects.get_or_create(
                promotion_rule=site_discount_rule,
                is_sitewide=True,
                defaults={
                    "is_active": True,
                    "priority": 50
                }
            )
            
            self.stdout.write(self.style.SUCCESS("✅ 促銷規則與關聯建立完成"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"建立促銷規則與關聯時發生錯誤: {e}"))

        self.stdout.write(self.style.SUCCESS("✅ 白蝦測試資料建立完成"))