from django.urls import path
from .views import InitiatePaymentView, PaymentStatusView, ReleasePaymentView

urlpatterns = [
    path('payment/create', InitiatePaymentView.as_view(), name='payment-create'),
    path('payment/status/<int:pk>', PaymentStatusView.as_view(), name='payment-status'),
    path('payment/release', ReleasePaymentView.as_view(), name='payment-release'),
]
