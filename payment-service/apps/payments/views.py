from rest_framework import views, status, permissions, generics
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Payment
from apps.orders.models import Order
from .serializers import PaymentSerializer, InitiatePaymentSerializer

class InitiatePaymentView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        order_id = serializer.validated_data['order_id']
        method = serializer.validated_data['payment_method']
        
        order = get_object_or_404(Order, id=order_id, buyer=request.user)
        
        # Create Payment Record
        payment, created = Payment.objects.get_or_create(
            order=order,
            defaults={
                'payment_method': method,
                'payment_amount': order.total_amount,
                'payment_status': Payment.Status.PENDING # Default
            }
        )
        
        # Integration Logic usually goes here (e.g. call MoMo API)
        # For MVP, we simulate success or return pending
        
        return Response({
            'message': 'Payment initiated',
            'payment_id': payment.id,
            'status': payment.payment_status
        }, status=status.HTTP_201_CREATED)

class PaymentStatusView(generics.RetrieveAPIView):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Allow buyer or seller to view
        return Payment.objects.filter(
            models.Q(order__buyer=self.request.user) | 
            models.Q(order__store__user=self.request.user)
        )

class ReleasePaymentView(views.APIView):
    # This might be automatic or admin triggered, or via confirm-receipt
    permission_classes = [permissions.IsAdminUser] # Restricted for now

    def post(self, request):
        payment_id = request.data.get('payment_id')
        payment = get_object_or_404(Payment, id=payment_id)
        
        if payment.payment_status == Payment.Status.COMPLETED: # Held
            payment.payment_status = Payment.Status.RELEASED
            payment.save()
            return Response({'status': 'released'})
        return Response({'error': 'Cannot release funds'}, status=status.HTTP_400_BAD_REQUEST)
