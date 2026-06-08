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
            order_id=order_id,
            defaults={
                'payment_method': method,
                'payment_amount': order.total_amount,
                'payment_status': Payment.Status.PENDING # Default
            }
        )
        
        # Integration Logic
        redirect_url = None
        if method == 'pesapal':
            from .services import pesapal_service
            try:
                pesapal_response = pesapal_service.submit_order(payment, order)
                payment.transaction_id = pesapal_response.get("order_tracking_id")
                payment.save()
                redirect_url = pesapal_response.get("redirect_url")
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'message': 'Payment initiated',
            'payment_id': payment.id,
            'status': payment.payment_status,
            'redirect_url': redirect_url
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

class PesapalIPNWebhookView(views.APIView):
    """
    Pesapal sends a POST request here when a payment completes or fails.
    """
    permission_classes = [permissions.AllowAny] # Webhook is public

    def post(self, request):
        order_tracking_id = request.query_params.get('OrderTrackingId') or request.data.get('OrderTrackingId')
        
        if not order_tracking_id:
            return Response({"error": "Missing OrderTrackingId"}, status=status.HTTP_400_BAD_REQUEST)

        from .services import pesapal_service
        try:
            # 1. Ask Pesapal what the true status of this transaction is
            status_data = pesapal_service.get_transaction_status(order_tracking_id)
            payment_status_code = status_data.get('status_code')
            
            # 2. Find our local Payment record
            payment = get_object_or_404(Payment, transaction_id=order_tracking_id)
            order = payment.order
            
            # 3. Update our Payment based on Pesapal's status
            # Pesapal status codes: 0=INVALID, 1=COMPLETED, 2=FAILED, 3=REVERSED
            if payment_status_code == 1:
                payment.payment_status = Payment.Status.COMPLETED
                payment.save()
                
                # Update Order to PAID
                order.payment_status = 'paid'
                order.status = 'confirmed' # Or whatever logic
                order.save()
            elif payment_status_code in [0, 2, 3]:
                payment.payment_status = Payment.Status.FAILED
                payment.save()
                
                order.payment_status = 'failed'
                order.save()

            # 4. Acknowledge the IPN so Pesapal stops retrying
            return Response({
                "orderNotificationType": request.data.get("OrderNotificationType"),
                "orderTrackingId": order_tracking_id,
                "orderMerchantReference": request.data.get("OrderMerchantReference"),
                "status": 200
            })
            
        except Exception as e:
            # If we fail, return 500 so Pesapal retries later
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
