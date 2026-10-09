"""
Marketplace admin API (admin.ubuntunow.rw).

* Admin sign-in is two-step: password, then a one-time code emailed to the admin.
* Every endpoint is permission-checked on the server (see shared admin_permissions).
* Only super admins can create, change or remove other admins.
* Sensitive actions are written to the audit log.
"""
from datetime import timedelta

from django.contrib.auth import password_validation
from django.contrib.auth.models import update_last_login
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.services.otp_service import create_email_otp, verify_email_otp
from shared.core.utils.admin_permissions import (
    ALL_PERMISSIONS,
    MANAGE_SELLERS,
    MANAGE_USERS,
    PERMISSION_CHOICES,
    VIEW_AUDIT_LOG,
    AdminPermission,
    IsSuperAdmin,
    has_admin_permission,
)
from shared.core.utils.internal import IsInternalService

from . import audit
from .models import AuditLog, User
from .serializers import (
    AdminUserCreateSerializer,
    AdminUserSerializer,
    CustomTokenObtainPairSerializer,
    UserDetailSerializer,
)

ADMIN_ACCESS_TOKEN_MINUTES = 10
ADMIN_REFRESH_TOKEN_HOURS = 8
LOGIN_CHALLENGE_SALT = 'admin-login-challenge'
LOGIN_CHALLENGE_MAX_AGE = 300  # seconds, same as the OTP lifetime

# Which permission lets an admin manage accounts of each role.
ROLE_PERMISSION = {User.Role.BUYER: MANAGE_USERS, User.Role.SELLER: MANAGE_SELLERS}

# Timing-equalisation target for unknown emails.
_DUMMY_HASH = User().password or 'pbkdf2_sha256$1$x$x'


def manageable_roles(user):
    """Roles of non-admin accounts this admin may see and manage."""
    return [role for role, perm in ROLE_PERMISSION.items() if has_admin_permission(user, perm)]


def _validate_permission_ids(value):
    unknown = sorted(set(value) - set(ALL_PERMISSIONS))
    if unknown:
        raise serializers.ValidationError(f"Unknown permissions: {', '.join(unknown)}")
    return list(dict.fromkeys(value))


# ── Sign-in (password + emailed code) ─────────────────────────────────────────

def _mask_email(email):
    name, _, domain = email.partition('@')
    return f"{name[:2]}{'*' * max(len(name) - 2, 1)}@{domain}"


class AdminLoginView(APIView):
    """Step 1: verify email + password, then email a one-time code. No tokens yet."""
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get('email', '')).strip()
        password = str(request.data.get('password', ''))
        user = User.objects.filter(email__iexact=email).first() if email else None

        # Always run one password check so response time doesn't reveal valid emails.
        valid = bool(user) and user.check_password(password)
        if not user:
            User().check_password(password)
        eligible = valid and user.is_active and user.role == User.Role.ADMIN and user.is_staff

        if not eligible:
            audit.record(request, 'admin.login.failed', 'user', getattr(user, 'id', ''),
                         {'email': email[:254]}, actor=user if valid else None)
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            create_email_otp(email=user.email, purpose='admin_login')
        except Exception:
            return Response({'detail': 'Could not send the verification code. Try again.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        challenge = signing.dumps({'uid': user.id}, salt=LOGIN_CHALLENGE_SALT)
        return Response({
            'otp_required': True,
            'challenge': challenge,
            'email_hint': _mask_email(user.email),
            'expires_in': LOGIN_CHALLENGE_MAX_AGE,
        })


def issue_admin_tokens(user):
    refresh = CustomTokenObtainPairSerializer.get_token(user)
    refresh['admin_session'] = True  # marks tokens that passed password + OTP
    refresh.set_exp(lifetime=timedelta(hours=ADMIN_REFRESH_TOKEN_HOURS))
    access = refresh.access_token
    access.set_exp(lifetime=timedelta(minutes=ADMIN_ACCESS_TOKEN_MINUTES))
    return str(refresh), str(access)


class AdminLoginVerifyView(APIView):
    """Step 2: exchange the challenge + emailed code for short-lived admin tokens."""
    permission_classes = [AllowAny]

    def post(self, request):
        challenge = request.data.get('challenge', '')
        otp = str(request.data.get('otp', '')).strip()
        try:
            uid = signing.loads(challenge, salt=LOGIN_CHALLENGE_SALT, max_age=LOGIN_CHALLENGE_MAX_AGE)['uid']
        except (signing.BadSignature, KeyError, TypeError):
            return Response({'detail': 'Sign-in expired. Please start again.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(id=uid, is_active=True, role=User.Role.ADMIN, is_staff=True).first()
        if not user:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            verify_email_otp(email=user.email, purpose='admin_login', raw_otp=otp)
        except ValidationError as exc:
            audit.record(request, 'admin.login.otp_failed', 'user', user.id, actor=user)
            detail = exc.detail[0] if isinstance(exc.detail, list) else exc.detail
            return Response({'detail': str(detail)}, status=status.HTTP_400_BAD_REQUEST)

        refresh, access = issue_admin_tokens(user)
        update_last_login(None, user)
        audit.record(request, 'admin.login', 'user', user.id, actor=user)
        return Response({'access': access, 'refresh': refresh, 'user': UserDetailSerializer(user).data})


# ── Token refresh (re-checks the database) ────────────────────────────────────

class DbBackedTokenRefreshView(APIView):
    """
    Replaces the stock refresh view. Claims are rebuilt from the database, so
    deactivated accounts stop working and permission changes take effect on the
    next refresh. Admin tokens stay short-lived and only refresh if they came
    from the password + OTP flow.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        invalid = Response({'detail': 'Token is invalid or expired', 'code': 'token_not_valid'},
                           status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(request.data.get('refresh', ''))
        except TokenError:
            return invalid

        user = User.objects.filter(id=refresh.get('user_id'), is_active=True).first()
        if not user:
            return invalid

        if user.role == User.Role.ADMIN:
            if not (user.is_staff and refresh.get('admin_session')):
                return invalid
            access = CustomTokenObtainPairSerializer.get_token(user).access_token
            access['admin_session'] = True
            access.set_exp(lifetime=timedelta(minutes=ADMIN_ACCESS_TOKEN_MINUTES))
        else:
            access = CustomTokenObtainPairSerializer.get_token(user).access_token
        return Response({'access': str(access)})


# ── Permission catalogue ──────────────────────────────────────────────────────

class AdminPermissionCatalogueView(APIView):
    permission_classes = [AdminPermission(*ALL_PERMISSIONS)]

    def get(self, request):
        return Response([{'id': pid, 'label': label} for pid, label in PERMISSION_CHOICES])


# ── Buyers & sellers ──────────────────────────────────────────────────────────

class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['is_active']


class AdminUserListView(generics.ListCreateAPIView):
    """
    GET  /users/admin/users/  — buyers and/or sellers the admin may manage
                                (super admins also see admins). ?role=&search=
    POST /users/admin/users/  — create a buyer or seller account.
    """
    permission_classes = [AdminPermission(MANAGE_USERS, MANAGE_SELLERS)]

    def get_serializer_class(self):
        return AdminUserCreateSerializer if self.request.method == 'POST' else AdminUserSerializer

    def visible_roles(self):
        roles = manageable_roles(self.request.user)
        if self.request.user.is_superuser:
            roles.append(User.Role.ADMIN)
        return roles

    def get_queryset(self):
        qs = User.objects.filter(role__in=self.visible_roles()).order_by('-date_joined')
        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(email__icontains=search)
        return qs

    def create(self, request, *args, **kwargs):
        role = request.data.get('role', User.Role.BUYER)
        if role == User.Role.ADMIN:
            raise PermissionDenied('Admin accounts are managed from the Admins section.')
        if role not in manageable_roles(request.user):
            raise PermissionDenied('You do not have permission to create this kind of account.')
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data['admin_permissions'] = []
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        audit.record(request, 'user.create', 'user', user.id, {'email': user.email, 'role': user.role})
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    """GET a user; PATCH {is_active} to deactivate / reactivate a buyer or seller."""
    permission_classes = [AdminPermission(MANAGE_USERS, MANAGE_SELLERS)]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_serializer_class(self):
        return AdminUserUpdateSerializer if self.request.method == 'PATCH' else AdminUserSerializer

    def get_queryset(self):
        roles = manageable_roles(self.request.user)
        if self.request.user.is_superuser:
            roles.append(User.Role.ADMIN)
        return User.objects.filter(role__in=roles)

    def update(self, request, *args, **kwargs):
        target = self.get_object()
        if target.role == User.Role.ADMIN:
            raise PermissionDenied('Admin accounts are managed from the Admins section.')
        if target.id == request.user.id:
            raise PermissionDenied('You cannot change your own account here.')
        serializer = AdminUserUpdateSerializer(target, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = target.is_active
        serializer.save()
        if before != target.is_active:
            audit.record(request, 'user.activate' if target.is_active else 'user.deactivate',
                         'user', target.id, {'email': target.email, 'role': target.role})
        return Response(AdminUserSerializer(target).data)


# ── Admin accounts (super admin only) ─────────────────────────────────────────

class AdminAccountCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    admin_permissions = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    class Meta:
        model = User
        fields = ['email', 'password', 'phone_number', 'admin_permissions']

    def validate_admin_permissions(self, value):
        return _validate_permission_ids(value)

    def validate(self, attrs):
        try:
            password_validation.validate_password(attrs['password'], User(email=attrs.get('email', '')))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        email = validated_data.pop('email')
        user = User.objects.create_user(
            email=email, username=email, password=password,
            role=User.Role.ADMIN, is_active=True, **validated_data,
        )
        user.is_staff = True  # admin accounts are staff; never super admins via the API
        user.save(update_fields=['is_staff'])
        return user


class AdminAccountUpdateSerializer(serializers.ModelSerializer):
    admin_permissions = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = User
        fields = ['admin_permissions', 'is_active']

    def validate_admin_permissions(self, value):
        return _validate_permission_ids(value)


class AdminAccountListCreateView(generics.ListCreateAPIView):
    """GET/POST /users/admin/admins/ — super admin only."""
    permission_classes = [IsSuperAdmin]

    def get_serializer_class(self):
        return AdminAccountCreateSerializer if self.request.method == 'POST' else AdminUserSerializer

    def get_queryset(self):
        return User.objects.filter(role=User.Role.ADMIN).order_by('-date_joined')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        audit.record(request, 'admin.create', 'user', user.id,
                     {'email': user.email, 'permissions': user.admin_permissions})
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminAccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /users/admin/admins/<id>/ — super admin only.
    Super admins themselves cannot be changed or removed through the API.
    """
    permission_classes = [IsSuperAdmin]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        return AdminAccountUpdateSerializer if self.request.method == 'PATCH' else AdminUserSerializer

    def get_queryset(self):
        return User.objects.filter(role=User.Role.ADMIN)

    def _guard(self, request, target):
        if target.is_superuser:
            raise PermissionDenied('Super admins cannot be modified here.')
        if target.id == request.user.id:
            raise PermissionDenied('You cannot modify your own account.')

    def update(self, request, *args, **kwargs):
        target = self.get_object()
        self._guard(request, target)
        before = {'permissions': list(target.admin_permissions), 'is_active': target.is_active}
        serializer = AdminAccountUpdateSerializer(target, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit.record(request, 'admin.update', 'user', target.id, {
            'email': target.email, 'before': before,
            'after': {'permissions': list(target.admin_permissions), 'is_active': target.is_active},
        })
        return Response(AdminUserSerializer(target).data)

    def destroy(self, request, *args, **kwargs):
        target = self.get_object()
        self._guard(request, target)
        info = {'email': target.email, 'permissions': list(target.admin_permissions)}
        target_id = target.id
        target.delete()
        audit.record(request, 'admin.delete', 'user', target_id, info)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Audit log ─────────────────────────────────────────────────────────────────

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'actor_id', 'actor_email', 'action', 'target_type', 'target_id',
                  'metadata', 'ip_address', 'created_at']


class AuditLogPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


class AuditLogListView(generics.ListAPIView):
    """GET /users/admin/audit/ ?action= &actor_id= &target_type="""
    permission_classes = [AdminPermission(VIEW_AUDIT_LOG)]
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination

    def get_queryset(self):
        qs = AuditLog.objects.all()
        params = self.request.query_params
        if params.get('action'):
            qs = qs.filter(action__icontains=params['action'])
        if params.get('actor_id', '').isdigit():
            qs = qs.filter(actor_id=int(params['actor_id']))
        if params.get('target_type'):
            qs = qs.filter(target_type=params['target_type'])
        return qs


class InternalAuditCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['actor_id', 'actor_email', 'action', 'target_type', 'target_id', 'metadata', 'ip_address']


class InternalAuditCreateView(generics.CreateAPIView):
    """Lets other services (e.g. payment-service) record audit entries. Internal only."""
    permission_classes = [IsInternalService]
    serializer_class = InternalAuditCreateSerializer
    authentication_classes = []
