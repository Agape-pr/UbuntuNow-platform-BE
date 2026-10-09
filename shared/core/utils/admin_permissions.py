"""
Admin role-based access control, shared by every service.

Admins are accounts with role == 'admin'. A super admin (is_superuser) can do
everything, including managing other admins. Other admins only get the
permissions listed in their ``admin_permissions`` (a list of the ids below).

Works with both the real auth-service User model and the stateless JWT user
used by the other services: both expose role / is_superuser / admin_permissions.
"""
from rest_framework.permissions import BasePermission

MANAGE_USERS = 'manage_users'          # buyers
MANAGE_SELLERS = 'manage_sellers'      # sellers & their stores
VIEW_ORDERS = 'view_orders'            # all orders (read-only)
MANAGE_PAYMENTS = 'manage_payments'    # payments, balance, escrow release
VIEW_AUDIT_LOG = 'view_audit_log'      # audit trail

PERMISSION_CHOICES = (
    (MANAGE_USERS, 'Manage Buyers'),
    (MANAGE_SELLERS, 'Manage Sellers & Stores'),
    (VIEW_ORDERS, 'View Orders'),
    (MANAGE_PAYMENTS, 'Manage Payments & Payouts'),
    (VIEW_AUDIT_LOG, 'View Audit Log'),
)
ALL_PERMISSIONS = [p for p, _ in PERMISSION_CHOICES]


def is_admin(user):
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_active', False)
        and getattr(user, 'role', None) == 'admin'
    )


def has_admin_permission(user, permission):
    if not is_admin(user):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return permission in (getattr(user, 'admin_permissions', None) or [])


def has_any_admin_permission(user, permissions):
    return any(has_admin_permission(user, p) for p in permissions)


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user) and bool(getattr(request.user, 'is_superuser', False))


def AdminPermission(*permissions):
    """Permission class factory: allow admins holding ANY of the given permissions."""
    class _AdminPermission(BasePermission):
        def has_permission(self, request, view):
            return has_any_admin_permission(request.user, permissions)
    _AdminPermission.__name__ = 'AdminPermission_' + '_'.join(permissions)
    return _AdminPermission
