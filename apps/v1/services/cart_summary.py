from decimal import Decimal
from django.db import models
from apps.v1.models import PromotionRule, PromotionRuleRelation, ActivityProduct, ProductDefaultPrice

def get_safe_original_price(product, activity=None):
    """
    取得商品原價：
    - 若有活動 → 優先回傳 ActivityProduct 的 original_price
    - 否則 → 回傳 default_price.price（容錯處理）
    """
    if activity:
        activity_product = ActivityProduct.objects.filter(activity=activity, product=product).first()
        if activity_product and activity_product.original_price is not None:
            return Decimal(activity_product.original_price)

    try:
        return Decimal(product.default_price.price)
    except ProductDefaultPrice.DoesNotExist:
        return Decimal("0")

def calculate_cart_summary(user, cart_items):
    """
    計算購物車摘要資訊 - 包含小計、各種折扣、最終金額、數量統計
    
    Args:
        user: 當前使用者
        cart_items: 購物車項目清單
        
    Returns:
        dict: 包含小計、折扣、最終金額、數量、贈品及適用規則等資訊
    """
    subtotal = 0
    item_discounts = 0
    order_discounts = 0
    final_total = 0
    total_quantity = 0
    total_gifts = 0
    applied_rules = []
    seen_rule_names = set()  # 👈 用於去重重複優惠名稱

    for cart_item in cart_items:
        product = cart_item.product
        quantity = cart_item.quantity
        activity = cart_item.activity

        # 原始價格
        if activity:
            try:
                activity_product = ActivityProduct.objects.get(activity=activity, product=product)
                original_price = activity_product.price
            except ActivityProduct.DoesNotExist:
                original_price = get_safe_original_price(cart_item.product, cart_item.activity)
        else:
            original_price = get_safe_original_price(cart_item.product, cart_item.activity)

        price = original_price
        gift_count = 0

        applicable_rules = PromotionRuleRelation.objects.filter(is_active=True).filter(
            models.Q(product=product) |
            models.Q(activity_product__product=product, activity_product__activity=activity) |
            (models.Q(activity=activity) if activity else models.Q(pk=None))  # ✅ 避免 activity=None 錯配
        ).order_by('-priority')

        for rule_rel in applicable_rules:
            rule = rule_rel.promotion_rule

            # 買贈
            if rule.rule_type == 'buy_gift' and rule.threshold_quantity and quantity >= rule.threshold_quantity:
                multiplier = quantity // rule.threshold_quantity
                gift_count += multiplier * (rule.gift_quantity or 0)

                gift_name = "相同商品" if rule.is_gift_same_product else getattr(rule.gift_product, "product_name", "贈品")
                rule_desc = f"{rule.name} (贈送{gift_name})"

                if rule_desc not in seen_rule_names:
                    applied_rules.append({"name": rule_desc, "type": "buy_gift"})
                    seen_rule_names.add(rule_desc)

            # 單品折扣
            elif rule.rule_type == 'buy_discount' and rule.discount_rate and quantity >= rule.threshold_quantity:
                price = original_price * (1 - rule.discount_rate)
                if rule.name not in seen_rule_names:
                    applied_rules.append({
                        "name": rule.name,
                        "type": "buy_discount",
                        "discount_rate": float(rule.discount_rate)
                    })
                    seen_rule_names.add(rule.name)

        item_subtotal = original_price * quantity
        item_final = price * quantity
        item_discount = item_subtotal - item_final

        subtotal += item_subtotal
        final_total += item_final
        item_discounts += item_discount
        total_quantity += quantity
        total_gifts += gift_count

    # 處理全站優惠
    free_shipping = False
    sitewide_rules = PromotionRuleRelation.objects.filter(is_active=True, is_sitewide=True).order_by('-priority')

    for rule_rel in sitewide_rules:
        rule = rule_rel.promotion_rule

        # 滿額折
        if rule.rule_type == 'order_discount' and rule.threshold_amount and subtotal >= rule.threshold_amount:
            if rule.discount_rate:
                discount = subtotal * rule.discount_rate
            elif rule.discount_amount:
                discount = rule.discount_amount
            else:
                discount = Decimal('0')

            order_discounts += discount
            final_total -= discount

            if rule.name not in seen_rule_names:
                applied_rules.append({
                    "name": rule.name,
                    "type": "order_discount",
                    "discount": float(discount)
                })
                seen_rule_names.add(rule.name)

        # 免運
        elif rule.rule_type == 'order_free_shipping':
            if ((rule.threshold_amount and subtotal >= rule.threshold_amount) or
                (rule.threshold_quantity and total_quantity >= rule.threshold_quantity)):
                if rule.name not in seen_rule_names:
                    applied_rules.append({
                        "name": rule.name,
                        "type": "free_shipping"
                    })
                    seen_rule_names.add(rule.name)
                free_shipping = True
                break

    final_total = max(Decimal('0'), final_total)

    return {
        "subtotal": float(subtotal),
        "itemDiscounts": float(item_discounts),
        "orderDiscounts": float(order_discounts),
        "finalAmount": float(final_total),
        "totalQuantity": total_quantity,
        "totalGifts": total_gifts,
        "freeShipping": free_shipping,
        "appliedRules": applied_rules
    }