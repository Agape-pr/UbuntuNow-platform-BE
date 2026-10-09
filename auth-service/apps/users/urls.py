from django.urls import path, re_path
from .views import (
    RegisterView,
    CurrentUserView,
    CustomTokenObtainPairView,
    AdminSetupView,
)
from .admin_api import (
    AdminLoginView,
    AdminLoginVerifyView,
    DbBackedTokenRefreshView,
    AdminPermissionCatalogueView,
    AdminUserListView,
    AdminUserDetailView,
    AdminAccountListCreateView,
    AdminAccountDetailView,
    AuditLogListView,
    InternalAuditCreateView,
)

urlpatterns = [
    path('register', RegisterView.as_view(), name='register'),
    path('login', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh', DbBackedTokenRefreshView.as_view(), name='token_refresh'),
    re_path(r'^me/?$', CurrentUserView.as_view(), name='user-me'),

    # Admin portal sign-in: password, then a one-time code emailed to the admin
    path('admin/login', AdminLoginView.as_view(), name='admin-login'),
    path('admin/login/verify', AdminLoginVerifyView.as_view(), name='admin-login-verify'),

    # Admin endpoints — each one is permission-checked (see shared admin_permissions)
    path('admin/permissions/', AdminPermissionCatalogueView.as_view(), name='admin-permissions'),
    path('admin/users/', AdminUserListView.as_view(), name='admin-user-list'),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin/admins/', AdminAccountListCreateView.as_view(), name='admin-account-list'),
    path('admin/admins/<int:pk>/', AdminAccountDetailView.as_view(), name='admin-account-detail'),
    path('admin/audit/', AuditLogListView.as_view(), name='admin-audit-log'),

    # Service-to-service (blocked at the gateway, requires the internal token)
    path('internal/audit/', InternalAuditCreateView.as_view(), name='internal-audit'),

    # One-time admin setup — secured by ADMIN_SETUP_SECRET env var
    path('admin/setup/', AdminSetupView.as_view(), name='admin-setup'),
]
