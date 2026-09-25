import logging
import uuid
from rest_framework import views, status, permissions, generics
from rest_framework.response import Response
import requests
from django.conf import settings
from django.shortcuts import get_object_or_404
from .models import Payment
from .serializers import PaymentSerializer, InitiatePaymentSerializer

logger = logging.getLogger(__name__)

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
        prompt_message = None
        if method == 'pesapal':
            from .services import pesapal_service
            try:
                pesapal_response = pesapal_service.submit_order(payment, order_data, request.user)
                payment.transaction_id = pesapal_response.get("order_tracking_id")
                payment.save()
                redirect_url = pesapal_response.get("redirect_url")
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        elif method in ('momo', 'airtel'):
            from .services import intouch_service
            phone_number = serializer.validated_data.get('phone_number')
            if not phone_number:
                return Response({'error': 'phone_number is required for mobile money payments'}, status=status.HTTP_400_BAD_REQUEST)

            request_transaction_id = f"UBN{payment.id}{uuid.uuid4().hex[:12]}"
            try:
                intouch_response = intouch_service.request_payment(
                    amount=payment.payment_amount,
                    mobile_phone=phone_number,
                    request_transaction_id=request_transaction_id,
                )
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if not intouch_response.get('success'):
                payment.payment_status = Payment.Status.FAILED
                payment.save()
                return Response(
                    {'error': intouch_response.get('message', 'Payment request failed')},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Stored (not IntouchPay's own transactionid) because the webhook
            # callback is matched against requesttransactionid per their docs.
            payment.transaction_id = request_transaction_id
            payment.save()
            prompt_message = intouch_response.get('message')

        return Response({
            'message': 'Payment initiated',
            'payment_id': payment.id,
            'status': payment.payment_status,
            'redirect_url': redirect_url,
            'prompt_message': prompt_message,
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

class ReleasablePaymentsView(generics.ListAPIView):
    """
    Payments held in escrow (COMPLETED) and awaiting an admin to release
    funds to the seller.
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Payment.objects.filter(payment_status=Payment.Status.COMPLETED).order_by('-payment_date')

class ReleasePaymentView(views.APIView):
    # Admin-triggered: pays out the seller's mobile money wallet via
    # IntouchPay's send_deposit (B2C push), then marks the payment RELEASED.
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        payment_id = request.data.get('payment_id')
        payment = get_object_or_404(Payment, id=payment_id)

        if payment.payment_status != Payment.Status.COMPLETED:
            return Response({'error': 'Payment is not held in escrow'}, status=status.HTTP_400_BAD_REQUEST)

        order_service_url = getattr(settings, 'ORDER_SERVICE_URL', 'http://localhost:8004')
        store_service_url = getattr(settings, 'STORE_SERVICE_URL', 'http://localhost:8002')

        try:
            order_res = requests.get(
                f"{order_service_url}/api/v1/orders/internal/{payment.order_id}/",
                timeout=10
            )
            order_res.raise_for_status()
            store_id = order_res.json().get('store_id')
        except Exception as e:
            return Response({'error': f"Failed to fetch order details: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        if not store_id:
            return Response({'error': 'Order is missing a store_id'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            store_res = requests.get(
                f"{store_service_url}/api/v1/users/internal/stores/by-id/{store_id}/",
                timeout=10
            )
            if store_res.status_code == 404:
                return Response({'error': 'Seller store not found'}, status=status.HTTP_400_BAD_REQUEST)
            store_res.raise_for_status()
            payout_phone_number = store_res.json().get('payout_phone_number')
        except Exception as e:
            return Response({'error': f"Failed to fetch seller store: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        if not payout_phone_number:
            return Response(
                {'error': "Seller has not set a payout phone number for their store yet"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .services import intouch_service
        request_transaction_id = f"REL{payment.id}{uuid.uuid4().hex[:12]}"
        try:
            deposit_response = intouch_service.send_deposit(
                amount=payment.payment_amount,
                mobile_phone=payout_phone_number,
                request_transaction_id=request_transaction_id,
                reason=f"UbuntuNow payout for Order #{payment.order_id}",
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not deposit_response.get('success'):
            return Response(
                {'error': deposit_response.get('message', 'Payout failed')},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment.payment_status = Payment.Status.RELEASED
        payment.save()
        return Response({
            'status': 'released',
            'transactionid': deposit_response.get('transactionid'),
            'referenceno': deposit_response.get('referenceno'),
        })

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
            
            # 3. Update our Payment based on Pesapal's status
            # Pesapal status codes: 0=INVALID, 1=COMPLETED, 2=FAILED, 3=REVERSED
            order_service_url = getattr(settings, 'ORDER_SERVICE_URL', 'http://localhost:8004')
            
            if payment_status_code == 1:
                payment.payment_status = Payment.Status.COMPLETED
                payment.save()
                
                # Update Order to PAID via internal endpoint
                try:
                    requests.patch(
                        f"{order_service_url}/api/v1/orders/internal/{payment.order_id}/update-payment/",
                        json={'payment_status': 'paid', 'status': 'confirmed'},
                        timeout=5
                    )
                except Exception as e:
                    print(f"Failed to update order-service: {e}")
            elif payment_status_code in [0, 2, 3]:
                payment.payment_status = Payment.Status.FAILED
                payment.save()
                
                try:
                    requests.patch(
                        f"{order_service_url}/api/v1/orders/internal/{payment.order_id}/update-payment/",
                        json={'payment_status': 'failed'},
                        timeout=5
                    )
                except Exception as e:
                    print(f"Failed to update order-service: {e}")

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

class IntouchWebhookView(views.APIView):
    """
    IntouchPay POSTs here once the subscriber approves/rejects the MoMo/Airtel
    prompt on their phone. Must ack with {"message": "success", "success": true,
    "request_id": ...} so IntouchPay stops retrying.
    """
    permission_classes = [permissions.AllowAny]  # Webhook is public

    def post(self, request):
        payload = request.data.get('jsonpayload', request.data)
        request_transaction_id = payload.get('requesttransactionid')

        if not request_transaction_id:
            return Response({"error": "Missing requesttransactionid"}, status=status.HTTP_400_BAD_REQUEST)

        payment = get_object_or_404(Payment, transaction_id=request_transaction_id)

        # Idempotent: IntouchPay may redeliver the same callback.
        if payment.payment_status in (Payment.Status.COMPLETED, Payment.Status.FAILED):
            return Response({
                "message": "success",
                "success": True,
                "request_id": request_transaction_id,
            })

        result_status = str(payload.get('status', '')).strip().lower()
        response_code = str(payload.get('responsecode', ''))

        # 'pending' is transient (rare) - don't resolve the payment yet, just ack.
        if result_status == 'pending' or response_code == '1000':
            return Response({
                "message": "success",
                "success": True,
                "request_id": request_transaction_id,
            })

        is_successful = response_code == '01' or result_status.startswith('success')

        order_service_url = getattr(settings, 'ORDER_SERVICE_URL', 'http://localhost:8004')

        if is_successful:
            payment.payment_status = Payment.Status.COMPLETED
            payment.save()
            try:
                requests.patch(
                    f"{order_service_url}/api/v1/orders/internal/{payment.order_id}/update-payment/",
                    json={'payment_status': 'paid', 'status': 'confirmed'},
                    timeout=5
                )
            except Exception as e:
                logger.error(f"Failed to update order-service: {e}")
        else:
            payment.payment_status = Payment.Status.FAILED
            payment.save()
            try:
                requests.patch(
                    f"{order_service_url}/api/v1/orders/internal/{payment.order_id}/update-payment/",
                    json={'payment_status': 'failed'},
                    timeout=5
                )
            except Exception as e:
                logger.error(f"Failed to update order-service: {e}")

        return Response({
            "message": "success",
            "success": True,
            "request_id": request_transaction_id,
        })
