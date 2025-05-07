# urls.py
from django.urls import path, include
from rest_framework import routers

from .views import (
    CategoryViewSet,
    ItemViewSet,
    ProductViewSet,
    BatchViewSet,
    ActivityViewSet,
    ActivityProductViewSet,
    CartViewSet,
    BannerViewSet,
    OrderViewSet,
    OrderItemViewSet,
    ProductWithPricingViewSet,
    PromotionRuleRelationViewSet,
    ShipmentItemViewSet,
    PromotionRuleViewSet,
    UserActivityLogViewSet,
    DashboardViewSet,
    MaterialCategoryViewSet,
    RecentHistoryView,
    CustomerServiceConfigViewSet, 
    CustomerServiceMessageViewSet, 
    CustomerServiceRequestViewSet, 
    FAQViewSet
)

# 使用DefaultRouter創建路由器
router = routers.DefaultRouter()

# 注册viewset到路由器，使用basename參數
router.register('category', CategoryViewSet, basename="category")
router.register('item', ItemViewSet, basename="item")  # 品號視圖集
router.register('material-category', MaterialCategoryViewSet, basename="material-category")  # 物料類別視圖集
router.register('product', ProductViewSet, basename="product")
router.register('batch', BatchViewSet, basename="batch")
router.register('activity', ActivityViewSet, basename="activity")
router.register('activity-product', ActivityProductViewSet, basename="activity-product")
router.register('cart', CartViewSet, basename="cart")
router.register('banner', BannerViewSet, basename="banner")
router.register('order', OrderViewSet, basename="order")
router.register('order-item', OrderItemViewSet, basename="order-item")
router.register('shipment-item', ShipmentItemViewSet, basename="shipment-item")
router.register('promotion-rule', PromotionRuleViewSet, basename="promotion-rule")
router.register('user-activity-log', UserActivityLogViewSet, basename="user-activity-log")
router.register('dashboard', DashboardViewSet, basename="dashboard")
router.register('products/with-pricing', ProductWithPricingViewSet, basename='product-with-pricing')
router.register('promotion-rule-relations', PromotionRuleRelationViewSet, basename='promotion-rule-relation')
router.register('customer-service/config', CustomerServiceConfigViewSet, basename="cs-config")
router.register('customer-service/requests', CustomerServiceRequestViewSet, basename="cs-request")
router.register('customer-service/messages', CustomerServiceMessageViewSet, basename="cs-message")
router.register('customer-service/faqs', FAQViewSet, basename="cs-faq")

# API URL配置
urlpatterns = [
    path('', include(router.urls)),
    path('recent_history/', RecentHistoryView.as_view(), name='recent-history'),
    # 這裡可以加入不屬於ViewSet的其他视图URL
]