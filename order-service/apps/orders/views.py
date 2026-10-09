from rest_framework import viewsets, mixins, permissions, status, decorators
from rest_framework.response import Response
from django.db import transaction
import logging
import requests
import os
from .models import Order, OrderItem
from rest_framework.pagination import PageNumberPagination
from .serializers import OrderSerializer, CheckoutSerializer, AdminOrderSerializer
from shared.core.utils.internal import IsInternalService, internal_headers
from shared.core.utils.admin_permissions import AdminPermission, VIEW_ORDERS

logger = logging.getLogger(__name__)


class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer
    http_method_names = ['get', 'post'] # Buyer can list or checkout (post)

    def get_queryset(self):
        return Order.objects.filter(buyer_id=self.request.user.id).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            logger.info("Checkout rejected: invalid payload %s", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        items_data = serializer.validated_data['items']
        delivery_address = serializer.validated_data.get('delivery_address')

        product_service_url = os.environ.get('PRODUCT_SERVICE_URL', 'http://product-service:8003')
        store_groups = {}

        # Fetch product data from product-service
        for item in items_data:
            product_id = item['product_id']
            qty = item['quantity']
            variations = item.get('selected_variations') or {}
            try:
                res = requests.get(f"{product_service_url}/api/v1/products/products/{product_id}/", timeout=5)
                if res.status_code != 200:
                    logger.warning("Checkout failed: product %s returned status %s", product_id, res.status_code)
                    return Response({'error': f"Product {product_id} not found"}, status=status.HTTP_400_BAD_REQUEST)
                product_data = res.json()
            except Exception as e:
                logger.exception("Checkout failed: product-service unreachable")
                return Response({'error': f"Failed to contact product service"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            if product_data.get('stock_quantity', 0) < qty:
                 logger.info("Checkout rejected: insufficient stock for product %s (stock %s, requested %s)", product_id, product_data.get('stock_quantity'), qty)
                 return Response({'error': f"Insufficient stock for {product_data.get('name')}"}, status=status.HTTP_400_BAD_REQUEST)
            
            store_id = product_data.get('store_id') or product_data.get('store')
            if type(store_id) is dict:
                store_id = store_id.get('id')
            
            if not store_id:
                return Response({'error': f"Product {product_id} is missing a store_id"}, status=status.HTTP_400_BAD_REQUEST)
                
            if store_id not in store_groups:
                store_groups[store_id] = []
            store_groups[store_id].append({
                'product': product_data,
                'quantity': qty,
                'selected_variations': variations
            })

        orders = []
        with transaction.atomic():
            for store_id, items in store_groups.items():
                total = sum(float(i['product'].get('price', 0)) * i['quantity'] for i in items)
                
                order = Order.objects.create(
                    buyer_id=request.user.id,
                    store_id=store_id,
                    total_amount=total,
                    delivery_address=delivery_address
                )
                
                for i in items:
                    prod = i['product']
                    qty = i['quantity']
                    variations = i.get('selected_variations') or {}
                    OrderItem.objects.create(
                        order=order,
                        product_id=prod.get('id'),
                        product_name=prod.get('name'),
                        quantity=qty,
                        price=prod.get('price'),
                        selected_variations=variations
                    )
                    
                    # Deduct stock via product-service
                    try:
                        # Assuming product-service has an endpoint to deduct stock, or we just patch it
                        new_stock = int(prod.get('stock_quantity', 0)) - qty
                        requests.patch(
                            f"{product_service_url}/api/v1/products/internal/stock/{prod.get('id')}/", 
                            json={'stock_quantity': new_stock},
                            headers=internal_headers(),
                            timeout=5
                        )
                    except Exception as e:
                        logger.exception("Failed to deduct stock for product %s", prod.get('id'))
                
                orders.append(order)
                
                # Publish Order Created Event
                try:
                    from shared.core.events import publish_event
                    publish_event(
                        exchange='ubuntunow.events',
                        routing_key='order.created',
                        message_dict={
                            'order_id': order.id,
                            'buyer_id': order.buyer_id,
                            'store_id': order.store_id,
                            'total_amount': str(order.total_amount),
                            'status': order.status
                        }
                    )
                except Exception as e:
                    logger.exception("Failed to publish order.created event")

        result_serializer = OrderSerializer(orders, many=True)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['post'], url_path='confirm-receipt')
    def confirm_receipt(self, request, pk=None):
        try:
            order = self.get_queryset().get(pk=pk)
        except Order.DoesNotExist:
             return Response(status=status.HTTP_404_NOT_FOUND)
             
        if order.status == Order.Status.SHIPPED:
             order.status = Order.Status.COMPLETED
             order.save()
             return Response({'status': 'confirmed'})
        return Response({'error': 'Order cannot be confirmed'}, status=status.HTTP_400_BAD_REQUEST)


class SellerOrderViewSet(viewsets.ReadOnlyModelViewSet):
    # Sellers can view orders and update status (via custom action)
    permission_classes = [permissions.IsAuthenticated] # + IsSeller check
    serializer_class = OrderSerializer

    def get_queryset(self):
        # We need store_id from JWT or user role.
        # StatelessUser stores it in request.user.store.id
        store_id = None
        store = getattr(self.request.user, 'store', None)
        if store and hasattr(store, 'id') and store.id:
            store_id = store.id
            
        if not store_id and getattr(self.request.user, 'role', None) == 'seller':
            import os
            import requests
            try:
                store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
                res = requests.get(f"{store_url}/api/v1/users/internal/stores/{self.request.user.id}/", headers=internal_headers(), timeout=2)
                if res.status_code == 200:
                    store_data = res.json()
                    if store_data.get('id'):
                        store_id = store_data.get('id')
            except Exception as e:
                logger.exception("Fallback store lookup failed")
                
        if store_id:
            return Order.objects.filter(store_id=store_id).order_by('-created_at')
        return Order.objects.none()

    @decorators.action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        if new_status in [Order.Status.SHIPPED, Order.Status.READY_FOR_PICKUP]:
            order.status = new_status
            order.save()
            return Response({'status': 'updated'})
        return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

class AdminOrderPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class AdminOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """All orders, read-only, for admins with the view_orders permission.
    Filters: ?status= &payment_status= &store_id= &buyer_id= &search=<order id>"""
    permission_classes = [AdminPermission(VIEW_ORDERS)]
    serializer_class = AdminOrderSerializer
    pagination_class = AdminOrderPagination

    def get_queryset(self):
        qs = Order.objects.all().prefetch_related('items').order_by('-created_at')
        params = self.request.query_params
        for field in ('status', 'payment_status'):
            if params.get(field):
                qs = qs.filter(**{field: params[field]})
        for field in ('store_id', 'buyer_id'):
            if params.get(field, '').isdigit():
                qs = qs.filter(**{field: int(params[field])})
        if params.get('search', '').lstrip('#').isdigit():
            qs = qs.filter(id=int(params['search'].lstrip('#')))
        return qs


class InternalOrderViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    # Internal service-to-service communication only: retrieve + update-payment.
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsInternalService]

    @decorators.action(detail=True, methods=['patch'], url_path='update-payment')
    def update_payment(self, request, pk=None):
        order = self.get_object()
        payment_status = request.data.get('payment_status')
        status_val = request.data.get('status')

        if payment_status and payment_status not in Order.PaymentStatus.values:
            return Response({'error': f"Invalid payment_status '{payment_status}'"}, status=status.HTTP_400_BAD_REQUEST)
        if status_val and status_val not in Order.Status.values:
            return Response({'error': f"Invalid status '{status_val}'"}, status=status.HTTP_400_BAD_REQUEST)

        newly_paid = payment_status == Order.PaymentStatus.PAID and order.payment_status != Order.PaymentStatus.PAID

        if payment_status:
            order.payment_status = payment_status
        if status_val:
            order.status = status_val
        order.save()

        if newly_paid:
            # Notify buyer and seller (consumed by notification-service). The real payment
            # webhooks land here, so this is where "payment secured" must be announced.
            try:
                from shared.core.events import publish_event
                publish_event(
                    exchange='ubuntunow.events',
                    routing_key='order.payment.held',
                    message_dict={
                        'order_id': order.id,
                        'buyer_id': order.buyer_id,
                        'store_id': order.store_id,
                        'total_amount': str(order.total_amount),
                        'status': order.status,
                        'payment_status': order.payment_status,
                    }
                )
            except Exception as e:
                logger.exception("Failed to publish order.payment.held event")

        return Response({'status': 'updated'})
