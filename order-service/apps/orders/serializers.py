from rest_framework import serializers
from .models import Order, OrderItem

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'product_id', 'product_name', 'quantity', 'price', 'selected_variations', 'subtotal']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'store_id', 'total_amount', 'status', 'payment_status', 'items', 'created_at']

class CheckoutItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    selected_variations = serializers.JSONField(required=False, allow_null=True)

class CheckoutSerializer(serializers.Serializer):
    items = CheckoutItemSerializer(many=True)
