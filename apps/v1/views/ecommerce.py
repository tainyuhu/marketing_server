from django.conf import settings
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q
from django.utils import timezone
from simple_history.utils import update_change_reason
from simple_history.models import HistoricalRecords
from ..services.simplified_order_services import generate_order_number
from decimal import Decimal
from django.db import transaction
import logging
import traceback
from utils.view import TrackedAPIView
from ..services.cart_summary import calculate_cart_summary
from ..models import (
    Product, ProductImage, Banner, Cart, CartItem, 
    Order, OrderItem, ShipmentItem, Item, Batch, Activity, Category, 
    MaterialCategory, PromotionRule, UserActivityLog, InventoryReservation, OrderInventoryLog
)
from ..serializers import (
    HistoricalRecordSerializer, ProductListSerializer, ProductDetailSerializer, 
    ProductCreateUpdateSerializer, ProductImageSerializer, CategoryProductCountSerializer,
    ProductWithPricingSerializer, CartItemSerializer, CartItemCreateSerializer,
    BannerSerializer, BannerResponseSerializer, OrderSerializer, OrderItemSerializer, 
    ShipmentItemSerializer, InventoryReservationSerializer, OrderInventoryLogSerializer
)
from ..filters import ProductFilter, OrderFilter
from .warehouse import ModelHistoryViewMixin

logger = logging.getLogger(__name__)


class ProductViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """商品視圖集"""
    queryset = Product.objects.all()
    serializer_class = ProductListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['product_code', 'product_name', 'description']
    ordering_fields = ['product_code', 'product_name', 'create_time', 'update_time']
    ordering = ['product_code']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        return ProductListSerializer
    
    @action(detail=True, methods=['get'], url_name='components', permission_classes=[IsAuthenticated])
    def components(self, request, pk=None):
        from ..serializers import ProductItemRelationSerializer
        product = self.get_object()
        components = ProductItemRelation.objects.filter(product=product)
        serializer = ProductItemRelationSerializer(components, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name='add_component', permission_classes=[IsAuthenticated])
    def add_component(self, request, pk=None):
        from ..serializers import ProductItemRelationSerializer
        from ..models import ProductItemRelation
        
        product = self.get_object()
        batch_id = request.data.get('batch')
        quantity = request.data.get('quantity', 1)
        unit = request.data.get('unit')

        try:
            batch = Batch.objects.get(pk=batch_id)
        except Batch.DoesNotExist:
            return Response({'error': '批號不存在'}, status=status.HTTP_404_NOT_FOUND)

        relation, created = ProductItemRelation.objects.get_or_create(
            product=product,
            batch=batch,
            defaults={
                'item': batch.item,
                'quantity': quantity,
                'unit': unit or batch.item.unit
            }
        )

        if not created:
            relation.quantity = quantity
            relation.unit = unit or batch.item.unit
            relation.save()

        serializer = ProductItemRelationSerializer(relation)
        return Response(serializer.data)

    @action(detail=True, methods=['delete'], url_name='remove_component', permission_classes=[IsAuthenticated])
    def remove_component(self, request, pk=None):
        from ..models import ProductItemRelation
        product = self.get_object()
        batch_id = request.data.get('batch')

        try:
            relation = ProductItemRelation.objects.get(product=product, batch_id=batch_id)
            relation.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProductItemRelation.DoesNotExist:
            return Response({'error': '該產品中找不到指定批號'}, status=status.HTTP_404_NOT_FOUND)
        
    @action(detail=True, methods=['post'], url_name='upload_image', permission_classes=[IsAuthenticated])
    def upload_image(self, request, pk=None):
        """上傳商品圖片"""
        product = self.get_object()
        image_url = request.data.get('image_url')
        sort_order = request.data.get('sort_order', 0)
        
        if not image_url:
            return Response({'error': '圖片URL不能為空'}, status=status.HTTP_400_BAD_REQUEST)
        
        product_image = ProductImage.objects.create(
            product=product,
            image_url=image_url,
            sort_order=sort_order
        )
        
        serializer = ProductImageSerializer(product_image)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_name='delete_image', permission_classes=[IsAuthenticated])
    def delete_image(self, request, pk=None):
        """刪除商品圖片"""
        product = self.get_object()
        image_id = request.data.get('image_id')
        
        if not image_id:
            return Response({'error': '圖片ID不能為空'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            image = ProductImage.objects.get(id=image_id, product=product)
            image.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProductImage.DoesNotExist:
            return Response({'error': '圖片不存在'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'], url_name='category_distribution', permission_classes=[IsAuthenticated])
    def category_distribution(self, request):
        """獲取類別分布統計"""
        stats = []
        total_count = Product.objects.count()
        
        if total_count == 0:
            return Response([])
        
        # 注意：這裡假設Product模型有一個與Category關聯的字段名為'category'
        categories = Category.objects.annotate(count=Count('product_set'))
        
        for category in categories:
            percentage = (category.count / total_count) * 100 if total_count > 0 else 0
            
            stats.append({
                'category_name': category.name,
                'product_count': category.count,
                'percentage': round(percentage, 2)
            })
        
        serializer = CategoryProductCountSerializer(stats, many=True)
        return Response(serializer.data)


class CartViewSet(viewsets.ViewSet):
    """購物車視圖集"""
    permission_classes = [IsAuthenticated]
    
    def get_cart(self, request):
        """獲取或創建用戶的購物車"""
        cart, created = Cart.objects.get_or_create(user=request.user)
        return cart
    
    @action(detail=False, methods=['get'], url_path='items')
    def items(self, request):
        """
        獲取購物車商品列表，包含優惠摘要與折扣後價格
        """
        cart = self.get_cart(request)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'activity')

        # ➕ 序列化商品資料
        serialized_items = CartItemSerializer(cart_items, many=True).data

        # ➕ 套用優惠計算摘要（使用 service 處理）
        summary = calculate_cart_summary(request.user, cart_items)

        return Response({
            'data': {
                'items': serialized_items,
                'summary': summary
            }
        })
    
    @action(detail=False, methods=['post'], url_path='add')
    def add(self, request):
        """添加商品到購物車"""
        serializer = CartItemCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            # 新增成功後直接返回購物車列表與 summary
            cart = self.get_cart(request)
            cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'activity')
            serialized_items = CartItemSerializer(cart_items, many=True).data
            summary = calculate_cart_summary(request.user, cart_items)
            return Response({
                'data': {
                    'items': serialized_items,
                    'summary': summary
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'data': {
                'success': False,
                'message': "添加失敗",
                'errors': serializer.errors
            }
        }, status=status.HTTP_400_BAD_REQUEST)

        
    @action(detail=False, methods=['put'], url_path='update')
    def update_item(self, request):
        """更新購物車中的商品數量"""
        cart = self.get_cart(request)
        product_id = request.data.get('productId')
        activity_id = request.data.get('activityId')
        quantity = request.data.get('quantity')

        if not product_id or quantity is None:
            return Response({
                'data': {
                    'success': False,
                    'message': "缺少必要參數"
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = CartItem.objects.get(
                cart=cart, 
                product_id=product_id, 
                activity_id=activity_id
            )
            cart_item.quantity = quantity
            cart_item.save()
        except CartItem.DoesNotExist:
            return Response({
                'data': {
                    'success': False,
                    'message': "指定商品不存在於購物車中"
                }
            }, status=status.HTTP_404_NOT_FOUND)

        cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'activity')
        serialized_items = CartItemSerializer(cart_items, many=True).data
        summary = calculate_cart_summary(request.user, cart_items)
        return Response({
            'data': {
                'items': serialized_items,
                'summary': summary
            }
        })
            
    @action(detail=False, methods=['delete'], url_path='remove')
    def remove_item(self, request):
        """從購物車中移除商品 - 使用購物車項目ID"""
        cart = self.get_cart(request)
        cart_item_id = request.data.get('id')
        
        if not cart_item_id:
            return Response({
                'data': {
                    'success': False,
                    'message': "缺少必要參數"
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 確保項目屬於當前用戶的購物車
            cart_item = CartItem.objects.get(id=cart_item_id, cart=cart)
            cart_item.delete()
        except CartItem.DoesNotExist:
            return Response({
                'data': {
                    'success': False,
                    'message': "指定商品不存在於購物車中"
                }
            }, status=status.HTTP_404_NOT_FOUND)
        
        cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'activity')
        serialized_items = CartItemSerializer(cart_items, many=True).data
        summary = calculate_cart_summary(request.user, cart_items)
        return Response({
            'data': {
                'items': serialized_items,
                'summary': summary
            }
        })
    
    @action(detail=False, methods=['get'], url_path='count')
    def count(self, request):
        """獲取購物車商品數量"""
        cart = self.get_cart(request)
        count = CartItem.objects.filter(cart=cart).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        return Response({
            'data': {
                'count': count
            }
        })
    
    @action(detail=False, methods=['delete'], url_path='clear')
    def clear(self, request):
        """清空購物車中的所有商品"""
        cart = self.get_cart(request)
        
        # 刪除該購物車中的所有項目
        CartItem.objects.filter(cart=cart).delete()
        
        # 返回清空後的購物車狀態
        return Response({
            'data': {
                'items': [],
                'summary': {
                    'subtotal': 0,
                    'itemDiscounts': 0,
                    'orderDiscounts': 0,
                    'finalAmount': 0,
                    'totalQuantity': 0,
                    'totalGifts': 0,
                    'freeShipping': False,
                    'appliedRules': []
                },
                'success': True,
                'message': '購物車已清空'
            }
        })


class BannerViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """橫幅視圖集"""
    queryset = Banner.objects.filter(is_active=True)
    serializer_class = BannerSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['priority', 'start_date']
    ordering = ['-priority', '-start_date']
    
    def get_serializer_class(self):
        if self.action == 'active':
            return BannerResponseSerializer
        return BannerSerializer
    
    @action(detail=False, methods=['get'], url_path='active')
    def active(self, request):
        """獲取當前活躍的橫幅"""
        now = timezone.now()
        
        # 獲取當前生效的、優先級最高的橫幅
        banner = Banner.objects.filter(
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
            is_deleted=False
        ).order_by('-priority', '-start_date').first()
        
        if not banner:
            return Response({'imageUrl': None})
        
        serializer = BannerResponseSerializer(banner)
        return Response(serializer.data)


class OrderViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """訂單視圖集"""
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderFilter
    search_fields = ['order_number', 'receiver_name', 'receiver_phone']
    ordering_fields = ['create_time', 'status', 'final_amount']
    ordering = ['-create_time']

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def create_order(self, request):
        """
        創建訂單並預留庫存（增強版）
        
        支援兩種請求格式:
        格式1（ID列表）:
        {
            "cart_items": [1, 2, 3],  # 購物車項目ID列表
            "shipping_info": {
                "name": "收件人姓名",
                "phone": "聯絡電話", 
                "address": "收件地址",
                "notes": "配送備註"
            }
        }
        
        格式2（完整物件）:
        {
            "cart_items": [
                {
                    "product": 79,
                    "quantity": 5,
                    "activity": 35,
                    ...
                }
            ],
            "address": {  # 或 shipping_info
                "name": "收件人姓名",
                "phone": "聯絡電話",
                "address": "收件地址",
                "notes": "配送備註"
            }
        }
        """
        user = request.user
        cart_items_data = request.data.get('cart_items', [])
        # 支援 'address' 或 'shipping_info' 作為鍵名
        shipping_info = request.data.get('shipping_info', {}) or request.data.get('address', {})
        
        # 檢查購物車項目格式並提取ID或創建購物車項目
        cart_item_ids = []
        if cart_items_data:
            # 如果是物件列表，需要創建或查找購物車項目
            if isinstance(cart_items_data[0], dict):
                cart = Cart.objects.get_or_create(user=user)[0]
                for item in cart_items_data:
                    # 檢查是否有購物車項目ID
                    if 'id' in item:
                        cart_item_ids.append(item['id'])
                    else:
                        # 根據產品和活動創建或更新購物車項目
                        try:
                            cart_item, created = CartItem.objects.get_or_create(
                                cart=cart,
                                product_id=item['product'],
                                activity_id=item.get('activity'),
                                defaults={'quantity': item.get('quantity', 1)}
                            )
                            if not created:
                                cart_item.quantity = item.get('quantity', 1)
                                cart_item.save()
                            cart_item_ids.append(cart_item.id)
                        except Exception as e:
                            logger.error(f"創建購物車項目失敗: {str(e)}")
                            return Response({
                                'data': {
                                    'success': False,
                                    'message': f'處理購物車項目失敗: {str(e)}'
                                }
                            }, status=status.HTTP_400_BAD_REQUEST)
            # 如果是ID列表，直接使用
            elif isinstance(cart_items_data[0], (int, str)):
                cart_item_ids = [int(item_id) for item_id in cart_items_data]
            else:
                return Response({
                    'data': {
                        'success': False,
                        'message': '購物車項目格式不正確'
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # 驗證購物車不為空
        if not cart_item_ids:
            return Response({
                'data': {
                    'success': False,
                    'message': '請選擇商品'
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 驗證收貨信息
        required_fields = ['name', 'phone', 'address']
        missing_fields = []
        for field in required_fields:
            if not shipping_info.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            return Response({
                'data': {
                    'success': False,
                    'message': f'收貨信息不完整，缺少: {", ".join(missing_fields)}'
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 獲取購物車項目
            cart_items = CartItem.objects.filter(
                id__in=cart_item_ids,
                cart__user=user
            ).select_related('product', 'activity')
            
            if not cart_items:
                return Response({
                    'data': {
                        'success': False,
                        'message': '未找到有效的購物車項目'
                    }
                }, status=status.HTTP_404_NOT_FOUND)
            
            # 調用增強版的庫存預留服務
            from ..services.order_services import create_order_with_inventory_reservation
            
            # 創建訂單（包含所有驗證和防重機制）
            order, error_message = create_order_with_inventory_reservation(user, cart_items, shipping_info)
            
            if not order:
                # 根據錯誤類型返回不同的狀態碼
                if error_message and ('庫存不足' in error_message or '超過最大購買數量' in error_message):
                    return Response({
                        'data': {
                            'success': False,
                            'message': error_message
                        }
                    }, status=status.HTTP_409_CONFLICT)  # 衝突錯誤
                elif error_message and '正在處理中' in error_message:
                    return Response({
                        'data': {
                            'success': False,
                            'message': error_message
                        }
                    }, status=status.HTTP_429_TOO_MANY_REQUESTS)  # 請求過於頻繁
                elif error_message and ('已下架' in error_message or '已停用' in error_message or '尚未開始' in error_message or '已結束' in error_message):
                    return Response({
                        'data': {
                            'success': False,
                            'message': error_message
                        }
                    }, status=status.HTTP_410_GONE)  # 資源不再可用
                else:
                    return Response({
                        'data': {
                            'success': False,
                            'message': error_message or '訂單創建失敗'
                        }
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # 訂單創建成功，清空購物車項目
            CartItem.objects.filter(id__in=cart_item_ids).delete()
            
            # 返回訂單信息
            serializer = OrderSerializer(order)
            return Response({
                'data': {
                    'success': True,
                    'message': '訂單創建成功，等待付款',
                    'order': serializer.data,
                    'payment_deadline': order.payment_deadline.isoformat() if order.payment_deadline else None
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            # 獲取詳細的錯誤信息
            error_traceback = traceback.format_exc()
            logger.error(f"創建訂單時發生錯誤: {str(e)}")
            logger.error(f"錯誤詳情: {error_traceback}")
            
            # 對不同的異常類型進行分類處理
            if 'OrderValidationError' in str(type(e)):
                logger.warning(f"訂單驗證錯誤: {str(e)}")
                return Response({
                    'data': {
                        'success': False,
                        'message': str(e)
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            elif 'OrderDuplicationError' in str(type(e)):
                logger.warning(f"訂單重複提交: {str(e)}")
                return Response({
                    'data': {
                        'success': False,
                        'message': '訂單正在處理中，請勿重複提交'
                    }
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)
            elif 'redis' in str(e).lower():
                logger.error(f"Redis 連接錯誤: {str(e)}")
                return Response({
                    'data': {
                        'success': False,
                        'message': 'Redis 服務暫時不可用，請稍後再試'
                    }
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            elif 'ProductItemRelation' in str(e) or 'Batch' in str(e):
                logger.error(f"庫存相關錯誤: {str(e)}")
                return Response({
                    'data': {
                        'success': False,
                        'message': '庫存系統錯誤，請聯繫管理員'
                    }
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                # 在開發環境中，可以返回詳細的錯誤信息
                if settings.DEBUG:
                    return Response({
                        'data': {
                            'success': False,
                            'message': f'系統錯誤: {str(e)}',
                            'traceback': error_traceback
                        }
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                else:
                    return Response({
                        'data': {
                            'success': False,
                            'message': '發生系統錯誤，請稍後再試'
                        }
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_name='confirm_payment', permission_classes=[IsAuthenticated])
    def confirm_payment(self, request, pk=None):
        """
        確認訂單付款
        
        請求格式:
        {
            "payment_info": {
                "method": "信用卡/銀行轉帳/...",
                "transaction_id": "交易編號",
                "amount": "付款金額"
            }
        }
        """
        order = self.get_object()
        
        # 確認是否為訂單擁有者或管理員
        if not request.user.is_staff and order.user != request.user:
            return Response({
                'data': {
                    'success': False,
                    'message': '無權操作此訂單'
                }
            }, status=status.HTTP_403_FORBIDDEN)
        
        # 檢查訂單狀態
        if order.status != 'pending_payment':
            return Response({
                'data': {
                    'success': False,
                    'message': f'訂單狀態不正確，當前狀態: {order.get_status_display()}'
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        payment_info = request.data.get('payment_info', {})
        
        # 調用確認付款服務
        from ..services.order_services import confirm_order_payment
        success, message = confirm_order_payment(order.id, payment_info)
        
        if not success:
            # 如果是付款期限已過，返回特定的狀態碼
            if '已超過付款期限' in message:
                return Response({
                    'data': {
                        'success': False,
                        'message': message
                    }
                }, status=status.HTTP_410_GONE)
            else:
                return Response({
                    'data': {
                        'success': False,
                        'message': message
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # 返回更新後的訂單信息
        order.refresh_from_db()
        serializer = OrderSerializer(order)
        return Response({
            'data': {
                'success': True,
                'message': '付款確認成功',
                'order': serializer.data
            }
        })
    
    @action(detail=True, methods=['post'], url_name='cancel_order', permission_classes=[IsAuthenticated])
    def cancel_order(self, request, pk=None):
        """
        取消訂單
        
        請求格式:
        {
            "reason": "取消原因"
        }
        """
        order = self.get_object()
        
        # 確認是否為訂單擁有者或管理員
        if not request.user.is_staff and order.user != request.user:
            return Response({
                'data': {
                    'success': False,
                    'message': '無權操作此訂單'
                }
            }, status=status.HTTP_403_FORBIDDEN)
        
        # 檢查訂單狀態
        if order.status not in ['pending_payment', 'paid']:
            return Response({
                'data': {
                    'success': False,
                    'message': f'訂單狀態不可取消，當前狀態: {order.get_status_display()}'
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        reason = request.data.get('reason', '用戶取消')
        
        # 調用取消訂單服務
        from ..services.order_services import cancel_order
        success, message = cancel_order(order.id, reason, request.user)
        
        if not success:
            return Response({
                'data': {
                    'success': False,
                    'message': message
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 返回更新後的訂單信息
        order.refresh_from_db()
        serializer = OrderSerializer(order)
        return Response({
            'data': {
                'success': True,
                'message': '訂單已取消',
                'order': serializer.data
            }
        })
    
    @action(detail=True, methods=['get'], url_name='inventory_reservations', permission_classes=[IsAuthenticated])
    def inventory_reservations(self, request, pk=None):
        """獲取訂單庫存預留記錄"""
        order = self.get_object()
        
        # 確認是否為訂單擁有者或管理員
        if not request.user.is_staff and order.user != request.user:
            return Response({
                'data': {
                    'success': False,
                    'message': '無權查看此訂單'
                }
            }, status=status.HTTP_403_FORBIDDEN)
        
        reservations = InventoryReservation.objects.filter(order=order).select_related('batch', 'item')
        serializer = InventoryReservationSerializer(reservations, many=True)
        return Response({
            'data': serializer.data
        })
    
    @action(detail=True, methods=['get'], url_name='inventory_logs', permission_classes=[IsAuthenticated])
    def inventory_logs(self, request, pk=None):
        """獲取訂單庫存操作日誌"""
        order = self.get_object()
        
        # 僅管理員可查看庫存操作日誌
        if not request.user.is_staff:
            return Response({
                'data': {
                    'success': False,
                    'message': '無權查看此操作日誌'
                }
            }, status=status.HTTP_403_FORBIDDEN)
        
        logs = OrderInventoryLog.objects.filter(order=order).select_related('batch', 'operator')
        serializer = OrderInventoryLogSerializer(logs, many=True)
        return Response({
            'data': serializer.data
        })
    
    @action(detail=True, methods=['get'], url_name='items', permission_classes=[IsAuthenticated])
    def items(self, request, pk=None):
        """獲取訂單的商品列表"""
        order = self.get_object()
        order_items = OrderItem.objects.filter(order=order)
        serializer = OrderItemSerializer(order_items, many=True)
        return Response({
            'data': serializer.data
        })
    
    @action(detail=True, methods=['get'], url_name='shipment_items', permission_classes=[IsAuthenticated])
    def shipment_items(self, request, pk=None):
        """獲取訂單的出貨明細"""
        order = self.get_object()
        # 先獲取所有訂單項目
        order_items = OrderItem.objects.filter(order=order)
        # 獲取所有出貨明細
        shipment_items = ShipmentItem.objects.filter(order_item__in=order_items)
        serializer = ShipmentItemSerializer(shipment_items, many=True)
        return Response({
            'data': serializer.data
        })
    
    @action(detail=True, methods=['post'], url_name='add_shipment', permission_classes=[IsAuthenticated])
    def add_shipment(self, request, pk=None):
        """添加出貨明細到訂單"""
        order = self.get_object()
        order_item_id = request.data.get('order_item')
        item_code = request.data.get('item_code')
        batch_number = request.data.get('batch_number')
        quantity = request.data.get('quantity')
        
        if not all([order_item_id, item_code, batch_number, quantity]):
            return Response({
                'data': {
                    'success': False,
                    'message': '缺少必要參數'
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order_item = OrderItem.objects.get(id=order_item_id, order=order)
        except OrderItem.DoesNotExist:
            return Response({
                'data': {
                    'success': False,
                    'message': '找不到指定的訂單項目'
                }
            }, status=status.HTTP_404_NOT_FOUND)
        
        # 創建出貨明細
        shipment_item = ShipmentItem.objects.create(
            order_item=order_item,
            item_code=item_code,
            batch_number=batch_number,
            quantity=quantity
        )
        
        serializer = ShipmentItemSerializer(shipment_item)
        return Response({
            'data': {
                'success': True,
                'message': '出貨明細添加成功',
                'shipment_item': serializer.data
            }
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_name='user_orders', permission_classes=[IsAuthenticated])
    def user_orders(self, request):
        """獲取當前用戶的訂單及其詳細項目信息"""
        user = request.user
        orders = Order.objects.filter(user=user).order_by('-create_time')
        
        page = self.paginate_queryset(orders)
        if page is not None:
            # 創建結果列表
            result = []
            for order in page:
                # 獲取訂單基本信息
                order_data = OrderSerializer(order).data
                
                # 獲取訂單項目
                order_items = OrderItem.objects.filter(order=order).select_related('product', 'activity')
                order_items_data = []
                
                for item in order_items:
                    # 序列化每個訂單項目
                    item_data = OrderItemSerializer(item).data
                    
                    # 添加商品圖片URL
                    if item.product:
                        item_data['image_url'] = item.product.main_image_url
                        
                        # 可選：獲取更多的商品圖片
                        product_images = ProductImage.objects.filter(product=item.product).order_by('sort_order')
                        if product_images.exists():
                            item_data['additional_images'] = [img.image_url for img in product_images]
                    
                    order_items_data.append(item_data)
                
                # 添加項目數據到訂單
                order_data['items'] = order_items_data
                result.append(order_data)
            
            # 返回帶有分頁的結果
            return self.get_paginated_response(result)
        
        # 無分頁時的處理
        result = []
        for order in orders:
            # 獲取訂單基本信息
            order_data = OrderSerializer(order).data
            
            # 獲取訂單項目
            order_items = OrderItem.objects.filter(order=order).select_related('product', 'activity')
            order_items_data = []
            
            for item in order_items:
                # 序列化每個訂單項目
                item_data = OrderItemSerializer(item).data
                
                # 添加商品圖片URL
                if item.product:
                    item_data['image_url'] = item.product.main_image_url
                    
                    # 可選：獲取更多的商品圖片
                    product_images = ProductImage.objects.filter(product=item.product).order_by('sort_order')
                    if product_images.exists():
                        item_data['additional_images'] = [img.image_url for img in product_images]
                
                order_items_data.append(item_data)
            
            # 添加項目數據到訂單
            order_data['items'] = order_items_data
            result.append(order_data)
        
        return Response({
            'data': result
        })

    @action(detail=False, methods=['get'], url_name='check_payment_deadline', permission_classes=[IsAuthenticated])
    def check_payment_deadline(self, request):
        """
        檢查用戶的待付款訂單付款期限
        返回即將過期的訂單列表
        """
        from datetime import timedelta
        
        user = request.user
        now = timezone.now()
        
        # 查詢待付款且即將過期的訂單（例如：1小時內）
        expiring_orders = Order.objects.filter(
            user=user,
            status='pending_payment',
            payment_deadline__isnull=False,
            payment_deadline__lte=now + timedelta(hours=1),
            payment_deadline__gt=now
        ).order_by('payment_deadline')
        
        serializer = OrderSerializer(expiring_orders, many=True)
        return Response({
            'data': {
                'expiring_orders': serializer.data,
                'message': f'您有 {expiring_orders.count()} 筆訂單即將過期'
            }
        })

    @action(detail=True, methods=['get'], url_name='order_detail', permission_classes=[IsAuthenticated])
    def order_detail(self, request, pk=None):
        """
        獲取訂單詳細信息，包括：
        - 訂單基本信息
        - 訂單項目
        - 庫存預留記錄
        - 出貨明細
        """
        order = self.get_object()
        
        # 確認是否為訂單擁有者或管理員
        if not request.user.is_staff and order.user != request.user:
            return Response({
                'data': {
                    'success': False,
                    'message': '無權查看此訂單'
                }
            }, status=status.HTTP_403_FORBIDDEN)
        
        # 獲取訂單基本信息
        order_serializer = OrderSerializer(order)
        
        # 獲取訂單項目
        order_items = OrderItem.objects.filter(order=order).select_related('product', 'activity')
        order_items_serializer = OrderItemSerializer(order_items, many=True)
        
        # 獲取庫存預留記錄
        reservations = InventoryReservation.objects.filter(order=order).select_related('batch', 'item')
        reservations_serializer = InventoryReservationSerializer(reservations, many=True)
        
        # 獲取出貨明細
        shipment_items = ShipmentItem.objects.filter(order_item__order=order).select_related('order_item')
        shipment_items_serializer = ShipmentItemSerializer(shipment_items, many=True)
        
        return Response({
            'data': {
                'order': order_serializer.data,
                'order_items': order_items_serializer.data,
                'inventory_reservations': reservations_serializer.data,
                'shipment_items': shipment_items_serializer.data
            }
        }) 

class OrderItemViewSet(TrackedAPIView, ModelHistoryViewMixin):
    """訂單項目視圖集"""
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """依照權限過濾訂單項目"""
        user = self.request.user
        # 如果是管理員，返回所有訂單項目
        if user.is_staff:
            return OrderItem.objects.all()
        # 否則只返回當前用戶的訂單項目
        return OrderItem.objects.filter(order__user=user)


class ShipmentItemViewSet(viewsets.ReadOnlyModelViewSet):
    """出貨明細視圖集 (唯讀)"""
    queryset = ShipmentItem.objects.all()
    serializer_class = ShipmentItemSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """依照權限過濾出貨明細"""
        user = self.request.user
        # 如果是管理員，返回所有出貨明細
        if user.is_staff:
            return ShipmentItem.objects.all()
        # 否則只返回當前用戶訂單的出貨明細
        return ShipmentItem.objects.filter(order_item__order__user=user)


class ProductWithPricingPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProductWithPricingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductWithPricingSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ProductWithPricingPagination

    def get_queryset(self):
        """依據 is_promotion 參數過濾資料"""
        queryset = super().get_queryset()
        is_promotion = self.request.query_params.get('is_promotion', None)

        if is_promotion == "true":
            queryset = queryset.filter(activities__activity__end_date__gte=timezone.now())
        elif is_promotion == "false":
            queryset = queryset.exclude(activities__activity__end_date__gte=timezone.now())

        return queryset.distinct()


class RecentHistoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class RecentHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = RecentHistoryPagination()

    def paginate_queryset(self, queryset, request, view=None):
        return self.pagination_class.paginate_queryset(queryset, request, view=view)

    def get_paginated_response(self, data):
        return self.pagination_class.get_paginated_response(data)

    def get(self, request):
        days = int(request.query_params.get('days', 7))
        model = request.query_params.get('model', None)
        user_id = request.query_params.get('user', None)

        since = timezone.now() - timezone.timedelta(days=days)

        all_history = []
        model_classes = [
            Item, Product, Batch, Activity, Order, OrderItem,
            Banner, Cart, PromotionRule, UserActivityLog,
            MaterialCategory, Category
        ]

        for model_cls in model_classes:
            history_model = model_cls.history.model
            qs = history_model.objects.filter(history_date__gte=since)
            if user_id:
                qs = qs.filter(history_user_id=user_id)
            if model:
                if model.lower() != model_cls.__name__.lower():
                    continue
            for record in qs:
                record._model_name = model_cls.__name__  # 附加模型名稱方便序列化顯示
                all_history.append(record)

        # 按時間排序
        all_history.sort(key=lambda r: r.history_date, reverse=True)

        page = self.paginate_queryset(all_history, request)
        serializer = HistoricalRecordSerializer(page, many=True)
        data = serializer.data

        # 附加模型名稱進去
        for i, record in enumerate(page):
            data[i]['model_name'] = getattr(record, '_model_name', 'Unknown')

        return self.get_paginated_response(data)


class DashboardViewSet(viewsets.ViewSet):
    """儀表板視圖集"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_name='statistics', permission_classes=[IsAuthenticated])
    def statistics(self, request):
        """獲取系統統計數據"""
        # 產品統計
        product_count = Product.objects.count()
        active_product_count = Product.objects.filter(is_deleted=False).count()
        
        # 庫存統計
        batch_count = Batch.objects.count()
        total_stock = Batch.objects.aggregate(total=Sum('quantity'))['total'] or 0
        low_stock_count = Batch.objects.filter(quantity__lte=10).count()
        expiring_count = Batch.objects.filter(
            expiry_date__lte=timezone.now().date() + timezone.timedelta(days=30),
            expiry_date__gt=timezone.now().date()
        ).count()
        
        # 訂單統計
        order_count = Order.objects.count()
        processing_order_count = Order.objects.filter(status='processing').count()
        shipped_order_count = Order.objects.filter(status='shipped').count()
        total_sales = Order.objects.filter(status__in=['completed', 'shipped']).aggregate(
            total=Sum('final_amount')
        )['total'] or 0
        
        # 活動統計
        active_activity_count = Activity.objects.filter(
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).count()
        
        return Response({
            'product': {
                'total': product_count,
                'active': active_product_count,
            },
            'stock': {
                'batch_count': batch_count,
                'total_quantity': total_stock,
                'low_stock': low_stock_count,
                'expiring_soon': expiring_count
            },
            'order': {
                'total': order_count,
                'processing': processing_order_count,
                'shipped': shipped_order_count,
                'total_sales': total_sales
            },
            'activity': {
                'active': active_activity_count
            }
        })
    
    @action(detail=False, methods=['get'], url_name='recent_orders', permission_classes=[IsAuthenticated])
    def recent_orders(self, request):
        """獲取最近訂單"""
        limit = int(request.query_params.get('limit', 5))
        orders = Order.objects.all().order_by('-create_time')[:limit]
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_name='top_products', permission_classes=[IsAuthenticated])
    def top_products(self, request):
        """獲取熱銷商品"""
        limit = int(request.query_params.get('limit', 5))
        
        # 計算各商品的銷售數量
        products_sold = OrderItem.objects.values('product').annotate(
            sold_quantity=Sum('quantity')
        ).order_by('-sold_quantity')[:limit]
        
        result = []
        for item in products_sold:
            try:
                product = Product.objects.get(id=item['product'])
                result.append({
                    'id': product.id,
                    'product_code': product.product_code,
                    'product_name': product.product_name,
                    'sold_quantity': item['sold_quantity'],
                    'main_image_url': product.main_image_url
                })
            except Product.DoesNotExist:
                pass
        
        return Response(result)