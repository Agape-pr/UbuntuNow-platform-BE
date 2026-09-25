from django.urls import path
from .views import (
    InitiatePaymentView,
    PaymentStatusView,
    IntouchBalanceView,
    ReleasablePaymentsView,
    ReleasePaymentView,
    PesapalIPNWebhookView,
    IntouchWebhookView,
)

urlpatterns = [
    path('payment/create', InitiatePaymentView.as_view(), name='payment-create'),
    path('payment/status/<int:pk>', PaymentStatusView.as_view(), name='payment-status'),
    path('payment/intouch-balance', IntouchBalanceView.as_view(), name='intouch-balance'),
    path('payment/releasable', ReleasablePaymentsView.as_view(), name='payment-releasable'),
    path('payment/release', ReleasePaymentView.as_view(), name='payment-release'),
    path('payment/webhook/pesapal/', PesapalIPNWebhookView.as_view(), name='pesapal-webhook'),
    path('payment/webhook/intouch/', IntouchWebhookView.as_view(), name='intouch-webhook'),
]
