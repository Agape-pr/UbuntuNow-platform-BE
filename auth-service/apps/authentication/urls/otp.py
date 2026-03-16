from django.urls import path
from apps.authentication.views.otp import (
    SendEmailOTPView,
    ResendEmailOTPView,
    VerifyEmailOTPView,
)

urlpatterns = [
    path("email/send/", SendEmailOTPView.as_view(), name="email-otp-send"),
    path("resend/", ResendEmailOTPView.as_view(), name="email-otp-resend"),
    path("verify/", VerifyEmailOTPView.as_view(), name="email-otp-verify"),
]
