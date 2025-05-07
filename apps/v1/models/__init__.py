# Import all models from warehouse.py
from .warehouse import (
    MaterialCategory,
    Item,
    Category,
    Batch,
    ProductItemRelation,
    InventoryReservation,  # 新增
)

# Import all models from ecommerce.py
from .ecommerce import (
    Product,
    ProductImage,
    ProductDefaultPrice,
    Banner,
    Cart,
    CartItem,
    Order,
    OrderItem,
    ShipmentItem,
    OrderInventoryLog,    # 新增
    OrderConfiguration,   # 新增
)

# Import all models from promotion.py
from .promotion import (
    Activity,
    ActivityProduct,
    PromotionRule,
    PromotionRuleRelation,
    UserActivityLog,
)


from .customer import (
    CustomerServiceConfig,
    CustomerServiceRequest,
    CustomerServiceMessage,
    FAQ
)



# For convenience, provide all models in a flat list
__all__ = [
    # Warehouse models
    'MaterialCategory',
    'Item',
    'Category',
    'Batch',
    'ProductItemRelation',
    'InventoryReservation',  # 新增
    
    # E-commerce models
    'Product',
    'ProductImage',
    'ProductDefaultPrice',
    'Banner',
    'Cart',
    'CartItem',
    'Order',
    'OrderItem',
    'ShipmentItem',
    'OrderInventoryLog',    # 新增
    'OrderConfiguration',   # 新增
    
    # Promotion models
    'Activity',
    'ActivityProduct',
    'PromotionRule',
    'PromotionRuleRelation',
    'UserActivityLog',

    'CustomerServiceConfig',
    'CustomerServiceRequest',
    'CustomerServiceMessage',
    'FAQ'
]