from rest_framework import viewsets, permissions, status, decorators
from rest_framework.response import Response
from django.db import transaction
import requests
import os
from .models import Order, OrderItem
from .serializers import OrderSerializer, CheckoutSerializer

class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer
    http_method_names = ['get', 'post'] # Buyer can list or checkout (post)

    def get_queryset(self):
        return Order.objects.filter(buyer_id=self.request.user.id).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            print(f"Checkout failed: Serializer validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        items_data = serializer.validated_data['items']

        product_service_url = os.environ.get('PRODUCT_SERVICE_URL', 'http://product-service:8003')
        store_groups = {}

        # Fetch product data from product-service
        for item in items_data:
            product_id = item['product_id']
            qty = item['quantity']
            try:
                res = requests.get(f"{product_service_url}/api/v1/products/products/{product_id}/", timeout=5)
                if res.status_code != 200:
                    print(f"Checkout failed: Product {product_id} returned status {res.status_code}")
                    return Response({'error': f"Product {product_id} not found"}, status=status.HTTP_400_BAD_REQUEST)
                product_data = res.json()
            except Exception as e:
                print(f"Checkout failed: Exception calling product service: {e}")
                return Response({'error': f"Failed to contact product service"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            if product_data.get('stock_quantity', 0) < qty:
                 print(f"Checkout failed: Insufficient stock for {product_data.get('name')}. Stock: {product_data.get('stock_quantity')}, Requested: {qty}")
                 return Response({'error': f"Insufficient stock for {product_data.get('name')}"}, status=status.HTTP_400_BAD_REQUEST)
            
            store_id = product_data.get('store') # Depending on how product serializer returns it
            if type(store_id) is dict:
                store_id = store_id.get('id')
                
            if store_id not in store_groups:
                store_groups[store_id] = []
            store_groups[store_id].append({
                'product': product_data,
                'quantity': qty
            })

        orders = []
        with transaction.atomic():
            for store_id, items in store_groups.items():
                total = sum(float(i['product'].get('price', 0)) * i['quantity'] for i in items)
                
                order = Order.objects.create(
                    buyer_id=request.user.id,
                    store_id=store_id,
                    total_amount=total
                )
                
                for i in items:
                    prod = i['product']
                    qty = i['quantity']
                    OrderItem.objects.create(
                        order=order,
                        product_id=prod.get('id'),
                        product_name=prod.get('name'),
                        quantity=qty,
                        price=prod.get('price')
                    )
                    
                    # Deduct stock via product-service
                    try:
                        # Assuming product-service has an endpoint to deduct stock, or we just patch it
                        new_stock = int(prod.get('stock_quantity', 0)) - qty
                        requests.patch(
                            f"{product_service_url}/api/v1/products/seller/products/{prod.get('id')}/", 
                            json={'stock_quantity': new_stock},
                            headers={'Authorization': request.headers.get('Authorization')},
                            timeout=5
                        )
                    except Exception as e:
                        print(f"Failed to deduct stock for {prod.get('id')}: {e}")
                
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
                    print(f"Failed to publish order created event: {e}")

        result_serializer = OrderSerializer(orders, many=True)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['post'], url_path='mock-payment')
    def mock_payment(self, request, pk=None):
        try:
            order = self.get_queryset().get(pk=pk)
        except Order.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
            
        if order.payment_status != Order.PaymentStatus.PENDING:
            return Response({'error': 'Order already paid or processed'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Simulate payment success
        order.payment_status = Order.PaymentStatus.HELD
        order.status = Order.Status.SHIPPED # Move to SHIPPED immediately for testing
        order.save()
        
        # Publish event for Notification Service
        event_data = {
            'order_id': order.id,
            'buyer_id': order.buyer_id,
            'store_id': order.store_id,
            'total_amount': str(order.total_amount),
            'status': order.status,
            'payment_status': order.payment_status,
        }
        try:
            from shared.core.events import publish_event
            publish_event(
                exchange='ubuntunow.events',
                routing_key='order.payment.held',
                message_dict=event_data
            )
        except Exception as e:
            print(f"Failed to publish mock payment event: {e}")
            
        return Response({'status': 'mock payment successful', 'payment_status': order.payment_status})

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
        # Assuming JWT provides store_id for sellers
        store_id = getattr(self.request.user, 'store_id', None)
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
