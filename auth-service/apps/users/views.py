from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import UserRegistrationSerializer, UserDetailSerializer, CustomTokenObtainPairSerializer

from apps.authentication.services.otp_service import create_email_otp


class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Register a new user and automatically send an email OTP
        for verification. The user remains inactive until the OTP
        is verified via the authentication endpoints.
        
        Returns response matching frontend RegisterResponse interface:
        {
            "email": string,
            "phone_number": string | null,
            "store": { store_name, store_description, store_logo } | null
        }
        """
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            # Return detailed validation errors for debugging
            return Response(
                {
                    "message": "Validation failed",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.save()

        # Automatically send OTP email for registration flow
        try:
            create_email_otp(email=user.email, purpose="register")
        except Exception:
            # Log error but don't fail registration if email fails
            # Frontend can still call sendOTP endpoint manually if needed
            pass

        # Build response matching frontend RegisterResponse interface
        data = {
            "email": user.email,
        }
        
        if user.phone_number:
            data["phone_number"] = user.phone_number
        
        # Include store data if user is a seller
        if user.is_seller() and hasattr(user, 'store'):
            store = user.store
            data["store"] = {
                "store_name": store.store_name,
            }
            if store.store_description:
                data["store"]["store_description"] = store.store_description
            if store.store_logo:
                data["store"]["store_logo"] = store.store_logo.url if hasattr(store.store_logo, 'url') else str(store.store_logo)

        return Response(data, status=status.HTTP_201_CREATED)

class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

