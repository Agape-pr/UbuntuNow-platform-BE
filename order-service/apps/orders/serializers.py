from rest_framework import serializers
from .models import Order, OrderItem
from apps.products.models import Product

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'subtotal']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    store_name = serializers.CharField(source='store.store_name', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'store', 'store_name', 'total_amount', 'status', 'payment_status', 'items', 'created_at']

class CheckoutItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)

class CheckoutSerializer(serializers.Serializer):
    items = CheckoutItemSerializer(many=True)
