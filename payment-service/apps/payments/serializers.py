from rest_framework import serializers
from .models import Payment

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'order', 'payment_method', 'payment_amount', 'payment_status', 'created_at']
        read_only_fields = ['payment_status', 'transaction_id']

class InitiatePaymentSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=Payment.Method.choices)
    phone_number = serializers.CharField(max_length=20) # For MoMo push
