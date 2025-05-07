# Warehouse related views
from .warehouse import (
    MaterialCategoryViewSet,
    CategoryViewSet,
    ItemViewSet,
    BatchViewSet
)

# Promotion related views
from .promotion import (
    ActivityViewSet,
    ActivityProductViewSet,
    PromotionRuleViewSet,
    PromotionRuleRelationViewSet,
    UserActivityLogViewSet
)

# E-commerce related views
from .ecommerce import (
    ProductViewSet,
    CartViewSet,
    BannerViewSet,
    OrderViewSet,
    OrderItemViewSet,
    ShipmentItemViewSet,
    ProductWithPricingViewSet,
    RecentHistoryView,
    DashboardViewSet
)

from .customer import(
    CustomerServiceConfigViewSet, CustomerServiceMessageViewSet, CustomerServiceRequestViewSet, FAQViewSet
)
