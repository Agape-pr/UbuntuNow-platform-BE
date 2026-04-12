from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    UserRegistrationSerializer,
    UserDetailSerializer,
    CustomTokenObtainPairSerializer,
    AdminUserSerializer,
)
from .models import User
from apps.authentication.services.otp_service import create_email_otp


class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Register a new user and automatically send an email OTP
        for verification. The user remains inactive until the OTP
        is verified via the authentication endpoints.
        """
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"message": "Validation failed", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.save()

        # Automatically send OTP email for registration flow
        try:
            create_email_otp(email=user.email, purpose="register")
        except Exception:
            pass

        data = {"email": user.email}
        if user.phone_number:
            data["phone_number"] = user.phone_number

        return Response(data, status=status.HTTP_201_CREATED)


class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# ── Admin Views ────────────────────────────────────────────────────────────────

class AdminUserListView(generics.ListAPIView):
    """
    GET /users/admin/users/
    Lists all users. Only accessible by staff/admin accounts.
    Query params:
      - role=seller|buyer|admin  (filter by role)
      - search=<email>           (partial email/username match)
    """
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = User.objects.all().order_by('-date_joined')

        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(email__icontains=search)

        return qs


class AdminUserDetailView(generics.RetrieveAPIView):
    """
    GET /users/admin/users/<id>/
    Returns full profile of a single user (including store for sellers).
    Only accessible by staff/admin accounts.
    """
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()
