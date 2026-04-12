from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
import os

from .serializers import (
    UserRegistrationSerializer,
    UserDetailSerializer,
    CustomTokenObtainPairSerializer,
    AdminUserSerializer,
    AdminUserCreateSerializer,
)
from .models import User
from apps.authentication.services.otp_service import create_email_otp


class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"message": "Validation failed", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = serializer.save()
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

class AdminUserListView(generics.ListCreateAPIView):
    """
    GET /users/admin/users/
    Requires is_staff=True. Filter by ?role=seller|buyer|admin, search by ?search=email
    
    POST /users/admin/users/
    Creates a new user. Requires is_superuser=True.
    """
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminUserCreateSerializer
        return AdminUserSerializer

    def create(self, request, *args, **kwargs):
        # Security Guard: Only superusers can create other admins/users
        if not request.user.is_superuser:
            return Response(
                {"error": "Only Super Admins can create new users and assign permissions."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)

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
    """GET /users/admin/users/<id>/ — requires is_staff=True"""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()


class AdminSetupView(APIView):
    """
    POST /users/admin/setup/
    Promotes an account to admin. Requires ADMIN_SETUP_SECRET env var.
    Body: { "email": "you@example.com", "secret": "<your-secret>" }
    Safe to ship permanently — does nothing without the correct secret.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        expected_secret = os.environ.get('ADMIN_SETUP_SECRET', '')
        if not expected_secret:
            return Response(
                {"error": "Admin setup not configured. Add ADMIN_SETUP_SECRET to Railway env vars."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        if request.data.get('secret', '') != expected_secret:
            return Response({"error": "Invalid secret."}, status=status.HTTP_403_FORBIDDEN)

        email = request.data.get('email', '').strip()
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": f"No user with email: {email}"}, status=status.HTTP_404_NOT_FOUND)

        user.is_staff = True
        user.is_superuser = True
        user.role = 'admin'
        user.save()

        return Response({
            "success": True,
            "message": f"{user.email} is now an admin.",
            "user": {"id": user.id, "email": user.email, "role": user.role}
        })
