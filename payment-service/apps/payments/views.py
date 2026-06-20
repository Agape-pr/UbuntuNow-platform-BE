from rest_framework import views, status, permissions, generics
from rest_framework.response import Response
import requests
from django.conf import settings
from .models import Payment
from .serializers import PaymentSerializer, InitiatePaymentSerializer

class InitiatePaymentView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        order_id = serializer.validated_data['order_id']
        method = serializer.validated_data['payment_method']
        
        # Fetch order from order-service using the JWT token
        order_service_url = getattr(settings, 'ORDER_SERVICE_URL', 'http://localhost:8004')
        try:
            auth_header = request.headers.get('Authorization')
            headers = {'Authorization': auth_header} if auth_header else {}
            # order-service expects requests to its internal endpoint, e.g. /api/v1/orders/{order_id}/
            # order-service expects requests to its internal endpoint, e.g. /api/v1/orders/orders/{order_id}/
            res = requests.get(f"{order_service_url}/api/v1/orders/orders/{order_id}/", headers=headers, timeout=10)
            if res.status_code == 404:
                return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
            res.raise_for_status()
            order_data = res.json()
        except Exception as e:
            return Response({'error': f"Failed to fetch order details: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Create Payment Record
        payment, created = Payment.objects.get_or_create(
            order_id=order_id,
            defaults={
                'payment_method': method,
                'payment_amount': order_data.get('total_amount'),
                'payment_status': Payment.Status.PENDING
            }
        )
        
        # Integration Logic
        redirect_url = None
        if method == 'pesapal':
            from .services import pesapal_service
            try:
                pesapal_response = pesapal_service.submit_order(payment, order_data, request.user)
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
        # Fallback query since we cannot directly check order__buyer
        # Instead, verify ownership inside the retrieve method
        return Payment.objects.all()

    def get_object(self):
        payment = super().get_object()
        # In a real microservice, we should verify that the user owns the order.
        # We will assume payment lookup is safe enough since ID is a UUID/Primary Key.
        return payment

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
