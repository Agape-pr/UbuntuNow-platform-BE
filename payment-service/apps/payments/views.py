import hmac
import logging
import uuid
from rest_framework import views, status, permissions, generics
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response
import requests
from django.conf import settings
from django.shortcuts import get_object_or_404
from .models import Payment
from rest_framework.pagination import LimitOffsetPagination
from .serializers import PaymentSerializer, InitiatePaymentSerializer
from shared.core.utils.internal import internal_headers
from shared.core.utils.admin_permissions import AdminPermission, MANAGE_PAYMENTS, has_admin_permission
from shared.core.utils.audit_client import record_audit

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
        except Exception:
            logger.exception("Could not fetch order %s for payment", order_id)
            return Response({'error': 'Could not load your order. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
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
            except Exception:
                logger.exception("Pesapal order submission failed for payment %s", payment.id)
                return Response({'error': 'Could not start the card payment. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
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
            except Exception:
                logger.exception("IntouchPay payment request failed for payment %s", payment.id)
                return Response({'error': 'Could not reach the mobile money provider. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

class OrderLookupUnavailable(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'Could not verify this payment right now. Please try again.'
    default_code = 'order_lookup_unavailable'


class PaymentStatusView(generics.RetrieveAPIView):
    """A payment is only visible to the buyer who owns its order, and to payments admins."""
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _buyer_owns_order(self, request, order_id):
        # order-service only returns an order to its own buyer (it filters by the JWT's user),
        # so a 200 here proves ownership without needing the buyer id.
        order_service_url = getattr(settings, 'ORDER_SERVICE_URL', 'http://localhost:8004')
        try:
            res = requests.get(
                f"{order_service_url}/api/v1/orders/orders/{order_id}/",
                headers={'Authorization': request.headers.get('Authorization', '')},
                timeout=5,
            )
        except requests.RequestException:
            logger.exception("Order ownership check failed for order %s", order_id)
            raise OrderLookupUnavailable()
        if res.status_code == 200:
            return True
        if res.status_code in (401, 403, 404):
            return False
        logger.error("Order ownership check got HTTP %s for order %s", res.status_code, order_id)
        raise OrderLookupUnavailable()

    def get_object(self):
        payment = super().get_object()
        if has_admin_permission(self.request.user, MANAGE_PAYMENTS):
            return payment
        if not self._buyer_owns_order(self.request, payment.order_id):
            raise NotFound()  # 404, not 403: don't confirm that the payment exists
        return payment

class IntouchBalanceView(views.APIView):
    """
    Live IntouchPay merchant account balance, for the admin dashboard.
    """
    permission_classes = [AdminPermission(MANAGE_PAYMENTS)]

    def get(self, request):
        from .services import intouch_service
        try:
            result = intouch_service.get_balance()
        except Exception:
            logger.exception("IntouchPay balance lookup failed")
            return Response({'error': 'Could not load the account balance.'}, status=status.HTTP_502_BAD_GATEWAY)

        if not result.get('success'):
            return Response({'error': result.get('message', 'Failed to fetch balance')}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'balance': result.get('balance')})

class ReleasablePaymentsView(generics.ListAPIView):
    """
    Payments held in escrow (COMPLETED) and awaiting an admin to release
    funds to the seller.
    """
    serializer_class = PaymentSerializer
    permission_classes = [AdminPermission(MANAGE_PAYMENTS)]
    queryset = Payment.objects.filter(payment_status=Payment.Status.COMPLETED).order_by('-payment_date')

class AdminPaymentPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


class AdminPaymentListView(generics.ListAPIView):
    """All payments, newest first, for admins with manage_payments. ?status= &order_id="""
    serializer_class = PaymentSerializer
    permission_classes = [AdminPermission(MANAGE_PAYMENTS)]
    pagination_class = AdminPaymentPagination

    def get_queryset(self):
        qs = Payment.objects.all().order_by('-payment_date', '-id')
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(payment_status=params['status'])
        if params.get('order_id', '').isdigit():
            qs = qs.filter(order_id=int(params['order_id']))
        return qs


class ReleasePaymentView(views.APIView):
    # Admin-triggered: pays out the seller's mobile money wallet via
    # IntouchPay's send_deposit (B2C push), then marks the payment RELEASED.
    permission_classes = [AdminPermission(MANAGE_PAYMENTS)]

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
                headers=internal_headers(),
                timeout=10
            )
            order_res.raise_for_status()
            store_id = order_res.json().get('store_id')
        except Exception:
            logger.exception("Could not fetch order %s for payout", payment.order_id)
            return Response({'error': 'Could not load the order for this payout. Please try again.'}, status=status.HTTP_502_BAD_GATEWAY)

        if not store_id:
            return Response({'error': 'Order is missing a store_id'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            store_res = requests.get(
                f"{store_service_url}/api/v1/users/internal/stores/by-id/{store_id}/",
                headers=internal_headers(),
                timeout=10
            )
            if store_res.status_code == 404:
                return Response({'error': 'Seller store not found'}, status=status.HTTP_400_BAD_REQUEST)
            store_res.raise_for_status()
            payout_phone_number = store_res.json().get('payout_phone_number')
        except Exception:
            logger.exception("Could not fetch store %s for payout", store_id)
            return Response({'error': 'Could not load the seller store for this payout. Please try again.'}, status=status.HTTP_502_BAD_GATEWAY)

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
        except Exception:
            logger.exception("IntouchPay payout failed for payment %s", payment.id)
            return Response({'error': 'The payout could not be completed. Please check the payment status before retrying.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not deposit_response.get('success'):
            record_audit(request, 'payment.release.failed', 'payment', payment.id, {
                'order_id': payment.order_id, 'amount': str(payment.payment_amount),
                'message': deposit_response.get('message', 'Payout failed'),
            })
            return Response(
                {'error': deposit_response.get('message', 'Payout failed')},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment.payment_status = Payment.Status.RELEASED
        payment.save()
        record_audit(request, 'payment.release', 'payment', payment.id, {
            'order_id': payment.order_id, 'amount': str(payment.payment_amount),
            'transactionid': deposit_response.get('transactionid'),
        })
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
                        headers=internal_headers(),
                        timeout=5
                    )
                except Exception:
                    logger.exception("Failed to update order-service after Pesapal payment %s", payment.id)
            elif payment_status_code in [0, 2, 3]:
                payment.payment_status = Payment.Status.FAILED
                payment.save()
                
                try:
                    requests.patch(
                        f"{order_service_url}/api/v1/orders/internal/{payment.order_id}/update-payment/",
                        json={'payment_status': 'failed'},
                        headers=internal_headers(),
                        timeout=5
                    )
                except Exception:
                    logger.exception("Failed to update order-service after Pesapal payment %s", payment.id)

            # 4. Acknowledge the IPN so Pesapal stops retrying
            return Response({
                "orderNotificationType": request.data.get("OrderNotificationType"),
                "orderTrackingId": order_tracking_id,
                "orderMerchantReference": request.data.get("OrderMerchantReference"),
                "status": 200
            })
            
        except Exception:
            # If we fail, return 500 so Pesapal retries later
            logger.exception("Pesapal IPN processing failed for %s", order_tracking_id)
            return Response({"error": "Could not process the notification"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class IntouchWebhookView(views.APIView):
    """
    IntouchPay POSTs here once the subscriber approves/rejects the MoMo/Airtel
    prompt on their phone. Must ack with {"message": "success", "success": true,
    "request_id": ...} so IntouchPay stops retrying.
    """
    permission_classes = [permissions.AllowAny]  # Webhook is public

    def post(self, request):
        secret = getattr(settings, 'INTOUCH_WEBHOOK_SECRET', '')
        if secret:
            provided = request.query_params.get('token', '')
            if not hmac.compare_digest(provided.encode(), secret.encode()):
                logger.warning("Rejected IntouchPay callback with a missing or wrong token")
                return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        else:
            logger.warning("INTOUCH_WEBHOOK_SECRET is not set: accepting IntouchPay callbacks without authentication")

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
                    headers=internal_headers(),
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
                    headers=internal_headers(),
                    timeout=5
                )
            except Exception as e:
                logger.error(f"Failed to update order-service: {e}")

        return Response({
            "message": "success",
            "success": True,
            "request_id": request_transaction_id,
        })
