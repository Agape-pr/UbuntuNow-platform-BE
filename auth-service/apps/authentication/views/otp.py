import logging

from django.contrib.auth import get_user_model

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.authentication.serializers.otp import SendEmailOTPSerializer
from apps.authentication.services.otp_service import create_email_otp

User = get_user_model()


logger = logging.getLogger(__name__)


class SendEmailOTPView(GenericAPIView):
    """
    Always answers the same way, whether or not the email belongs to an account, so this
    endpoint cannot be used to discover who is registered. A code is only actually sent when
    the request makes sense for the account (and not more than once per cooldown).
    """
    serializer_class = SendEmailOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]

        user = User.objects.filter(email=email).first()
        if purpose == "register":
            eligible = user is not None and not user.is_active
        else:  # login / reset_password
            eligible = user is not None and user.is_active

        if eligible:
            try:
                create_email_otp(email=email, purpose=purpose, enforce_cooldown=True)
            except Exception:
                # Never let a delivery problem reveal that the account exists.
                logger.exception("Could not send %s OTP", purpose)

        return Response({"email": email, "purpose": purpose}, status=status.HTTP_200_OK)


from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from apps.authentication.serializers.otp import ResendEmailOTPSerializer
from apps.authentication.services.otp_service import NoPendingOTP, resend_email_otp


class ResendEmailOTPView(GenericAPIView):
    serializer_class = ResendEmailOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]

        try:
            resend_email_otp(email=email, purpose=purpose)
        except NoPendingOTP:
            # Same answer as a successful resend: don't reveal whether a code is pending.
            pass

        # Return response matching frontend ResendOTPResponse interface
        return Response(
            {
                "email": email,
                "purpose": purpose,
            },
            status=status.HTTP_200_OK,
        )


from django.shortcuts import get_object_or_404

from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.serializers.otp import VerifyEmailOTPSerializer
from apps.authentication.services.otp_service import verify_email_otp

User = get_user_model()


class VerifyEmailOTPView(GenericAPIView):
    serializer_class = VerifyEmailOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        purpose = serializer.validated_data["purpose"]

        verify_email_otp(email=email, purpose=purpose, raw_otp=otp)

        user = get_object_or_404(User, email=email)

        if purpose == "register" and not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])

        if not user.is_active:
            return Response(
                {"detail": "Account not active"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Admins must sign in through the admin portal (password + emailed code).
        # An emailed code alone must never yield an admin session.
        if user.role == User.Role.ADMIN:
            return Response(
                {"detail": "Admin accounts must sign in through the admin portal."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from apps.users.serializers import CustomTokenObtainPairSerializer
        refresh = CustomTokenObtainPairSerializer.get_token(user)

        return Response(
            {
                "message": "OTP verified successfully",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                },
            },
            status=status.HTTP_200_OK,
        )


