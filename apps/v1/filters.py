# filters.py
import django_filters
from django.db.models import Q
from django.utils import timezone
from .models import (
    Item, Product, Batch, Activity, Order, MaterialCategory
)

class MaterialCategoryFilter(django_filters.FilterSet):
    """物料類別過濾器"""
    name = django_filters.CharFilter(lookup_expr='icontains')
    parent = django_filters.NumberFilter(field_name='parent', lookup_expr='exact')
    parent_isnull = django_filters.BooleanFilter(field_name='parent', lookup_expr='isnull')
    
    class Meta:
        model = MaterialCategory
        fields = ['name', 'parent', 'parent_isnull']

class ItemFilter(django_filters.FilterSet):
    """品號過濾器"""
    item_code = django_filters.CharFilter(lookup_expr='icontains')
    name = django_filters.CharFilter(lookup_expr='icontains')
    material_category = django_filters.NumberFilter(field_name='material_category', lookup_expr='exact')
    specification = django_filters.CharFilter(lookup_expr='icontains')
    status = django_filters.BooleanFilter()
    
    class Meta:
        model = Item
        fields = ['item_code', 'name', 'material_category', 'specification', 'status']


class ProductFilter(django_filters.FilterSet):
    """商品過濾器"""
    product_code = django_filters.CharFilter(lookup_expr='icontains')
    product_name = django_filters.CharFilter(lookup_expr='icontains')
    product_category = django_filters.CharFilter(lookup_expr='icontains')
    is_promotion = django_filters.BooleanFilter()
    tags = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.DateTimeFilter(field_name='create_time', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='create_time', lookup_expr='lte')
    
    class Meta:
        model = Product
        fields = [
            'product_code', 'product_name', 'product_category',
            'is_promotion', 'tags', 'created_after', 'created_before'
        ]


class BatchFilter(django_filters.FilterSet):
    """批號過濾器"""
    item = django_filters.NumberFilter(field_name='item')
    item_code = django_filters.CharFilter(field_name='item__item_code')
    batch_number = django_filters.CharFilter(lookup_expr='icontains')
    warehouse = django_filters.CharFilter(lookup_expr='icontains')
    location = django_filters.CharFilter(lookup_expr='icontains')
    state = django_filters.ChoiceFilter(
        choices=[
            ('active', '正常'), 
            ('locked', '鎖定'), 
            ('quarantine', '隔離'), 
            ('expired', '過期')
        ]
    )
    expiry_from = django_filters.DateFilter(field_name='expiry_date', lookup_expr='gte')
    expiry_to = django_filters.DateFilter(field_name='expiry_date', lookup_expr='lte')
    min_quantity = django_filters.NumberFilter(field_name='quantity', lookup_expr='gte')
    max_quantity = django_filters.NumberFilter(field_name='quantity', lookup_expr='lte')
    
    expiring_in_days = django_filters.NumberFilter(method='filter_expiring_in_days')
    
    def filter_expiring_in_days(self, queryset, name, value):
        """過濾指定天數內即將過期的批號"""
        if value is not None:
            today = timezone.now().date()
            expiry_date = today + timezone.timedelta(days=value)
            return queryset.filter(expiry_date__lte=expiry_date, expiry_date__gt=today)
        return queryset
    
    class Meta:
        model = Batch
        fields = [
            'item', 'item_code', 'batch_number', 'warehouse', 'location', 'state',
            'expiry_from', 'expiry_to', 'min_quantity', 'max_quantity',
            'expiring_in_days'
        ]

class ActivityFilter(django_filters.FilterSet):
    """活動過濾器"""
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_popular = django_filters.BooleanFilter(field_name='is_popular')
    is_discount_based = django_filters.BooleanFilter(field_name='is_discount_based')
    free_shipping = django_filters.BooleanFilter(field_name='free_shipping')
    min_progress = django_filters.NumberFilter(field_name='progress', lookup_expr='gte')
    max_progress = django_filters.NumberFilter(field_name='progress', lookup_expr='lte')
    start_from = django_filters.DateTimeFilter(field_name='start_date', lookup_expr='gte')
    start_to = django_filters.DateTimeFilter(field_name='start_date', lookup_expr='lte')
    end_from = django_filters.DateTimeFilter(field_name='end_date', lookup_expr='gte')
    end_to = django_filters.DateTimeFilter(field_name='end_date', lookup_expr='lte')
    
    is_active = django_filters.BooleanFilter(method='filter_active')
    is_upcoming = django_filters.BooleanFilter(method='filter_upcoming')
    is_ended = django_filters.BooleanFilter(method='filter_ended')
    
    def filter_active(self, queryset, name, value):
        """過濾當前有效的活動"""
        now = timezone.now()
        if value:
            return queryset.filter(start_date__lte=now, end_date__gte=now)
        return queryset
    
    def filter_upcoming(self, queryset, name, value):
        """過濾即將開始的活動"""
        now = timezone.now()
        if value:
            return queryset.filter(start_date__gt=now)
        return queryset
    
    def filter_ended(self, queryset, name, value):
        """過濾已結束的活動"""
        now = timezone.now()
        if value:
            return queryset.filter(end_date__lt=now)
        return queryset
    
    class Meta:
        model = Activity
        fields = [
            'name', 'is_popular', 'is_discount_based', 'free_shipping',
            'min_progress', 'max_progress', 'start_from', 'start_to', 
            'end_from', 'end_to', 'is_active', 'is_upcoming', 'is_ended'
        ]


class OrderFilter(django_filters.FilterSet):
    """訂單過濾器"""
    order_number = django_filters.CharFilter(lookup_expr='icontains')
    status = django_filters.ChoiceFilter(choices=[
        ('pending', '待處理'),
        ('processing', '處理中'),
        ('shipped', '已出貨'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    ])
    user = django_filters.NumberFilter()
    receiver_name = django_filters.CharFilter(lookup_expr='icontains')
    receiver_phone = django_filters.CharFilter(lookup_expr='icontains')
    min_amount = django_filters.NumberFilter(field_name='final_amount', lookup_expr='gte')
    max_amount = django_filters.NumberFilter(field_name='final_amount', lookup_expr='lte')
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    
    class Meta:
        model = Order
        fields = [
            'order_number', 'status', 'user', 'receiver_name', 'receiver_phone',
            'min_amount', 'max_amount', 'created_after', 'created_before'
        ]