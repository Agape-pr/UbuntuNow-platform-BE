from rest_framework import viewsets, permissions, status, decorators
from rest_framework.response import Response
from django.db import transaction
from .models import Order, OrderItem
from apps.products.models import Product
from .serializers import OrderSerializer, CheckoutSerializer

class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer
    http_method_names = ['get', 'post'] # Buyer can list or checkout (post)

    def get_queryset(self):
        return Order.objects.filter(buyer=self.request.user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        # Checkout Logic
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        items_data = serializer.validated_data['items']
        product_ids = [item['product_id'] for item in items_data]
        products = Product.objects.in_bulk(product_ids)

        # Group by store
        store_groups = {}
        for item in items_data:
            product = products.get(item['product_id'])
            if not product:
                return Response({'error': f"Product {item['product_id']} not found"}, status=status.HTTP_400_BAD_REQUEST)
            if product.stock_quantity < item['quantity']:
                 return Response({'error': f"Insufficient stock for {product.name}"}, status=status.HTTP_400_BAD_REQUEST)
            
            store_id = product.store.id
            if store_id not in store_groups:
                store_groups[store_id] = []
            store_groups[store_id].append({
                'product': product,
                'quantity': item['quantity']
            })

        orders = []
        with transaction.atomic():
            for store_id, items in store_groups.items():
                # Calculate total
                total = sum(i['product'].price * i['quantity'] for i in items)
                store = items[0]['product'].store # Get store instance from first product

                order = Order.objects.create(
                    buyer=request.user,
                    store=store,
                    total_amount=total
                )
                
                for i in items:
                    product = i['product']
                    qty = i['quantity']
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=qty,
                        price=product.price
                    )
                    # Deduct stock
                    product.stock_quantity -= qty
                    product.save()
                
                orders.append(order)

        result_serializer = OrderSerializer(orders, many=True)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['post'], url_path='confirm-receipt')
    def confirm_receipt(self, request, pk=None):
        try:
            order = self.get_queryset().get(pk=pk)
        except Order.DoesNotExist:
             return Response(status=status.HTTP_404_NOT_FOUND)
             
        if order.status == Order.Status.SHIPPED: # Or whatever logic
             order.status = Order.Status.COMPLETED
             order.save()
             # Trigger payment release logic here (call Payment Service)
             return Response({'status': 'confirmed'})
        return Response({'error': 'Order cannot be confirmed'}, status=status.HTTP_400_BAD_REQUEST)


class SellerOrderViewSet(viewsets.ReadOnlyModelViewSet):
    # Sellers can view orders and update status (via custom action)
    permission_classes = [permissions.IsAuthenticated] # + IsSeller check
    serializer_class = OrderSerializer

    def get_queryset(self):
        if self.request.user.is_seller():
            return Order.objects.filter(store__user=self.request.user).order_by('-created_at')
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
