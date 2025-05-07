# admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import ActivityProduct, Product, Batch, ProductItemRelation
from .utils import recalculate_all_activity_product_stock

class ProductItemRelationInline(admin.TabularInline):
    model = ProductItemRelation
    extra = 1
    fields = ('item', 'batch', 'quantity', 'unit', 'get_batch_stock')
    readonly_fields = ('get_batch_stock',)
    
    def get_batch_stock(self, obj):
        if obj and obj.batch:
            return obj.batch.quantity
        return "-"
    get_batch_stock.short_description = "批號庫存"

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_code', 'product_name', 'is_deleted')
    search_fields = ('product_code', 'product_name')
    inlines = [ProductItemRelationInline]
    
    actions = ['recalculate_related_activity_products']
    
    def recalculate_related_activity_products(self, request, queryset):
        updated_count = 0
        for product in queryset:
            activity_products = ActivityProduct.objects.filter(product=product)
            for ap in activity_products:
                old_stock = ap.stock
                new_stock = ap.calculate_available_stock()
                if old_stock != new_stock:
                    ActivityProduct.objects.filter(id=ap.id).update(stock=new_stock)
                    updated_count += 1
        
        self.message_user(request, f"已更新 {updated_count} 個活動商品的庫存")
    recalculate_related_activity_products.short_description = "重新計算選中商品的活動庫存"

@admin.register(ActivityProduct)
class ActivityProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'activity', 'product', 'price', 'stock', 'calculated_stock', 'stock_status')
    list_filter = ('activity',)
    search_fields = ('product__product_name', 'activity__name')
    readonly_fields = ('calculated_stock',)
    
    actions = ['recalculate_stock', 'sync_calculated_stock']
    
    def calculated_stock(self, obj):
        return obj.calculate_available_stock()
    calculated_stock.short_description = "計算庫存"
    
    def stock_status(self, obj):
        calculated = obj.calculate_available_stock()
        current = obj.stock
        
        if calculated == current:
            return format_html('<span style="color: green;">✓ 一致</span>')
        return format_html('<span style="color: red;">✗ 不一致 (實際: {}, 設定: {})</span>', calculated, current)
    stock_status.short_description = "庫存狀態"
    
    def recalculate_stock(self, request, queryset):
        """顯示計算後的庫存，但不更新"""
        for ap in queryset:
            calculated = ap.calculate_available_stock()
            self.message_user(request, f"ID {ap.id}: {ap.product.product_name} - 計算庫存: {calculated}, 當前設定: {ap.stock}")
    recalculate_stock.short_description = "檢查庫存計算結果"
    
    def sync_calculated_stock(self, request, queryset):
        """將庫存更新為計算後的值"""
        updated_count = 0
        for ap in queryset:
            old_stock = ap.stock
            new_stock = ap.calculate_available_stock()
            if old_stock != new_stock:
                ActivityProduct.objects.filter(id=ap.id).update(stock=new_stock)
                updated_count += 1
        
        self.message_user(request, f"已同步 {updated_count} 個活動商品的庫存")
    sync_calculated_stock.short_description = "同步為計算庫存"

# 添加全局管理動作
def recalculate_all_stock(modeladmin, request, queryset):
    """Admin action to recalculate all ActivityProduct stock"""
    updated_count = recalculate_all_activity_product_stock()
    modeladmin.message_user(request, f"已更新 {updated_count} 個活動商品的庫存")

# 註冊全局動作到 admin site
admin.site.add_action(recalculate_all_stock, '重新計算所有活動商品庫存')