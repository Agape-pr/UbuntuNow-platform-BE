from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    CurrentUserView,
    CustomTokenObtainPairView,
    AdminUserListView,
    AdminUserDetailView,
    AdminSetupView,
)

urlpatterns = [
    path('register', RegisterView.as_view(), name='register'),
    path('login', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', CurrentUserView.as_view(), name='user-me'),

    # Admin endpoints — requires is_staff=True
    path('admin/users/', AdminUserListView.as_view(), name='admin-user-list'),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),

    # One-time admin setup — secured by ADMIN_SETUP_SECRET env var
    path('admin/setup/', AdminSetupView.as_view(), name='admin-setup'),
]
