from django.contrib.auth import get_user_model

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.authentication.serializers.otp import SendEmailOTPSerializer
from apps.authentication.services.otp_service import create_email_otp

User = get_user_model()


class SendEmailOTPView(GenericAPIView):
    serializer_class = SendEmailOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]

        user = User.objects.filter(email=email).first()

        if purpose == "register":
            if not user:
                return Response(
                    {"detail": "User not found. Please register first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user.is_active:
                return Response(
                    {"detail": "User already verified."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if purpose in ["login", "reset_password"] and not user:
            return Response(
                {"detail": "User does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        create_email_otp(email=email, purpose=purpose)

        # Return response matching frontend SendOTPResponse interface
        return Response(
            {
                "email": email,
                "purpose": purpose,
            },
            status=status.HTTP_200_OK,
        )



from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from apps.authentication.serializers.otp import ResendEmailOTPSerializer
from apps.authentication.services.otp_service import resend_email_otp


class ResendEmailOTPView(GenericAPIView):
    serializer_class = ResendEmailOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]

        resend_email_otp(email=email, purpose=purpose)

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

        refresh = RefreshToken.for_user(user)

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


