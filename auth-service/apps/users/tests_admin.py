import os
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.users.models import AuditLog, User

PASSWORD = 'Str0ng-Passw0rd!x'


def make_user(email, role='buyer', perms=None, superuser=False, active=True):
    user = User.objects.create_user(
        username=email, email=email, password=PASSWORD, role=role,
        is_active=active, admin_permissions=perms or [],
    )
    if role == 'admin':
        user.is_staff = True
    user.is_superuser = superuser
    user.save()
    return user


def bearer(user, admin_session=True):
    refresh = RefreshToken.for_user(user)
    refresh['role'] = user.role
    refresh['is_superuser'] = user.is_superuser
    refresh['admin_permissions'] = user.admin_permissions
    if admin_session:
        refresh['admin_session'] = True
    return refresh


class AdminTestBase(TestCase):
    def setUp(self):
        # Seller serialisation calls store-service over HTTP; keep tests offline.
        patcher = mock.patch('apps.users.serializers.requests.get', side_effect=ConnectionError)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': 'test-token'})
        env.start()
        self.addCleanup(env.stop)

        self.super = make_user('root@example.com', 'admin', superuser=True)
        self.buyer = make_user('buyer@example.com', 'buyer')
        self.seller = make_user('seller@example.com', 'seller')
        self.client = APIClient()

    def as_user(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {bearer(user).access_token}')
        return self.client


class AdminLoginTests(AdminTestBase):
    def start_login(self, email='root@example.com', password=PASSWORD):
        with mock.patch('apps.authentication.services.otp_service.send_otp_email') as send:
            resp = self.client.post('/api/v1/users/admin/login', {'email': email, 'password': password}, format='json')
        return resp, send

    def test_password_alone_gives_no_tokens_and_sends_code(self):
        resp, send = self.start_login()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['otp_required'])
        self.assertNotIn('access', resp.json())
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs['purpose'], 'admin_login')

    def test_bad_credentials_and_non_admins_get_same_401(self):
        for email, pw in [('root@example.com', 'wrong'), ('nobody@example.com', PASSWORD), ('buyer@example.com', PASSWORD)]:
            resp, send = self.start_login(email, pw)
            self.assertEqual(resp.status_code, 401, email)
            self.assertEqual(resp.json(), {'detail': 'Invalid credentials.'})
            send.assert_not_called()
        self.assertTrue(AuditLog.objects.filter(action='admin.login.failed').exists())

    def test_inactive_admin_cannot_start_login(self):
        make_user('off@example.com', 'admin', active=False)
        resp, _ = self.start_login('off@example.com')
        self.assertEqual(resp.status_code, 401)

    def test_full_login_issues_short_lived_admin_tokens(self):
        resp, send = self.start_login()
        challenge = resp.json()['challenge']
        otp = send.call_args.kwargs['otp']

        bad = self.client.post('/api/v1/users/admin/login/verify', {'challenge': challenge, 'otp': '000000'}, format='json')
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post('/api/v1/users/admin/login/verify', {'challenge': challenge, 'otp': otp}, format='json')
        self.assertEqual(ok.status_code, 200)
        body = ok.json()
        access = AccessToken(body['access'])
        self.assertEqual(access['role'], 'admin')
        self.assertTrue(access['is_superuser'])
        self.assertTrue(access['admin_session'])
        self.assertLessEqual(access['exp'] - access['iat'], 10 * 60)
        self.assertEqual(body['user']['email'], 'root@example.com')
        self.assertTrue(AuditLog.objects.filter(action='admin.login', actor_id=self.super.id).exists())

        # The code is single use.
        again = self.client.post('/api/v1/users/admin/login/verify', {'challenge': challenge, 'otp': otp}, format='json')
        self.assertEqual(again.status_code, 400)

    def test_verify_rejects_forged_challenge(self):
        resp = self.client.post('/api/v1/users/admin/login/verify', {'challenge': 'forged', 'otp': '123456'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_normal_login_refuses_admin_accounts(self):
        resp = self.client.post('/api/v1/users/login', {'username': 'root@example.com', 'password': PASSWORD}, format='json')
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn('access', resp.json())

    def test_normal_login_still_works_for_buyers(self):
        resp = self.client.post('/api/v1/users/login', {'username': 'buyer@example.com', 'password': PASSWORD}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.json())


class TokenRefreshTests(AdminTestBase):
    def refresh(self, token):
        return self.client.post('/api/v1/users/token/refresh', {'refresh': str(token)}, format='json')

    def test_buyer_refresh_returns_access_only(self):
        resp = self.refresh(bearer(self.buyer, admin_session=False))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.json()), ['access'])

    def test_deactivated_user_cannot_refresh(self):
        token = bearer(self.buyer, admin_session=False)
        self.buyer.is_active = False
        self.buyer.save()
        self.assertEqual(self.refresh(token).status_code, 401)

    def test_garbage_token_rejected(self):
        self.assertEqual(self.refresh('nonsense').status_code, 401)

    def test_admin_refresh_requires_otp_session(self):
        self.assertEqual(self.refresh(bearer(self.super, admin_session=False)).status_code, 401)
        self.assertEqual(self.refresh(bearer(self.super, admin_session=True)).status_code, 200)

    def test_permission_changes_apply_on_refresh(self):
        sub = make_user('sub@example.com', 'admin', perms=['manage_users'])
        token = bearer(sub)
        sub.admin_permissions = ['view_orders']
        sub.save()
        access = AccessToken(self.refresh(token).json()['access'])
        self.assertEqual(access['admin_permissions'], ['view_orders'])
        self.assertLessEqual(access['exp'] - access['iat'], 10 * 60)

    def test_demoted_admin_cannot_refresh(self):
        sub = make_user('sub@example.com', 'admin', perms=['manage_users'])
        token = bearer(sub)
        sub.is_staff = False
        sub.save()
        self.assertEqual(self.refresh(token).status_code, 401)


class UserManagementPermissionTests(AdminTestBase):
    LIST = '/api/v1/users/admin/users/'

    def emails(self, user):
        resp = self.as_user(user).get(self.LIST)
        self.assertEqual(resp.status_code, 200, resp.content)
        return sorted(u['email'] for u in resp.json())

    def test_visibility_follows_permissions(self):
        buyers_admin = make_user('a1@example.com', 'admin', perms=['manage_users'])
        sellers_admin = make_user('a2@example.com', 'admin', perms=['manage_sellers'])
        both = make_user('a3@example.com', 'admin', perms=['manage_users', 'manage_sellers'])
        self.assertEqual(self.emails(buyers_admin), ['buyer@example.com'])
        self.assertEqual(self.emails(sellers_admin), ['seller@example.com'])
        self.assertEqual(self.emails(both), ['buyer@example.com', 'seller@example.com'])
        self.assertIn('root@example.com', self.emails(self.super))

    def test_admin_without_relevant_permission_is_blocked(self):
        orders_only = make_user('a4@example.com', 'admin', perms=['view_orders'])
        self.assertEqual(self.as_user(orders_only).get(self.LIST).status_code, 403)
        no_perms = make_user('a5@example.com', 'admin')
        self.assertEqual(self.as_user(no_perms).get(self.LIST).status_code, 403)

    def test_non_admin_roles_are_blocked_even_with_permission_claims(self):
        sneaky = make_user('s@example.com', 'seller', perms=['manage_users'])
        self.assertEqual(self.as_user(sneaky).get(self.LIST).status_code, 403)
        self.assertEqual(self.as_user(self.buyer).get(self.LIST).status_code, 403)
        self.assertEqual(self.client.__class__().get(self.LIST).status_code, 401)

    def test_deactivate_is_scoped_by_permission_and_audited(self):
        buyers_admin = make_user('a1@example.com', 'admin', perms=['manage_users'])
        c = self.as_user(buyers_admin)
        self.assertEqual(c.patch(f'{self.LIST}{self.seller.id}/', {'is_active': False}, format='json').status_code, 404)
        resp = c.patch(f'{self.LIST}{self.buyer.id}/', {'is_active': False}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_active)
        entry = AuditLog.objects.get(action='user.deactivate')
        self.assertEqual((entry.actor_id, entry.target_id), (buyers_admin.id, str(self.buyer.id)))

    def test_patch_only_changes_is_active(self):
        c = self.as_user(self.super)
        c.patch(f'{self.LIST}{self.buyer.id}/', {'is_active': True, 'role': 'admin', 'is_superuser': True}, format='json')
        self.buyer.refresh_from_db()
        self.assertEqual((self.buyer.role, self.buyer.is_superuser), ('buyer', False))

    def test_cannot_manage_admins_or_self_through_user_endpoint(self):
        sub = make_user('a1@example.com', 'admin', perms=['manage_users'])
        c = self.as_user(self.super)
        self.assertEqual(c.patch(f'{self.LIST}{sub.id}/', {'is_active': False}, format='json').status_code, 403)
        self.assertEqual(c.patch(f'{self.LIST}{self.super.id}/', {'is_active': False}, format='json').status_code, 403)

    def test_create_user_respects_permissions(self):
        buyers_admin = make_user('a1@example.com', 'admin', perms=['manage_users'])
        c = self.as_user(buyers_admin)
        body = {'email': 'new@example.com', 'password': PASSWORD, 'role': 'buyer'}
        self.assertEqual(c.post(self.LIST, body, format='json').status_code, 201)
        self.assertEqual(c.post(self.LIST, {**body, 'email': 'n2@example.com', 'role': 'seller'}, format='json').status_code, 403)
        self.assertEqual(c.post(self.LIST, {**body, 'email': 'n3@example.com', 'role': 'admin'}, format='json').status_code, 403)
        self.assertFalse(User.objects.filter(email='n3@example.com').exists())
        self.assertEqual(AuditLog.objects.filter(action='user.create').count(), 1)


class AdminAccountTests(AdminTestBase):
    LIST = '/api/v1/users/admin/admins/'

    def test_only_super_admin_can_manage_admins(self):
        sub = make_user('a1@example.com', 'admin', perms=['manage_users', 'manage_sellers', 'view_audit_log'])
        c = self.as_user(sub)
        self.assertEqual(c.get(self.LIST).status_code, 403)
        body = {'email': 'x@example.com', 'password': PASSWORD, 'admin_permissions': ['manage_users']}
        self.assertEqual(c.post(self.LIST, body, format='json').status_code, 403)
        self.assertEqual(self.as_user(self.buyer).get(self.LIST).status_code, 403)

    def test_super_admin_creates_admin_with_permissions(self):
        body = {'email': 'new-admin@example.com', 'password': PASSWORD, 'admin_permissions': ['manage_users', 'view_orders']}
        resp = self.as_user(self.super).post(self.LIST, body, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        user = User.objects.get(email='new-admin@example.com')
        self.assertEqual((user.role, user.is_staff, user.is_superuser), ('admin', True, False))
        self.assertEqual(user.admin_permissions, ['manage_users', 'view_orders'])
        self.assertTrue(AuditLog.objects.filter(action='admin.create', target_id=str(user.id)).exists())

    def test_rejects_unknown_permissions_and_weak_passwords(self):
        c = self.as_user(self.super)
        r = c.post(self.LIST, {'email': 'x@example.com', 'password': PASSWORD, 'admin_permissions': ['root']}, format='json')
        self.assertEqual(r.status_code, 400)
        r = c.post(self.LIST, {'email': 'y@example.com', 'password': '12345678', 'admin_permissions': []}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(email__in=['x@example.com', 'y@example.com']).exists())

    def test_update_permissions_and_deactivate(self):
        sub = make_user('a1@example.com', 'admin', perms=['manage_users'])
        c = self.as_user(self.super)
        r = c.patch(f'{self.LIST}{sub.id}/', {'admin_permissions': ['view_orders'], 'is_active': False}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        sub.refresh_from_db()
        self.assertEqual((sub.admin_permissions, sub.is_active), (['view_orders'], False))
        self.assertEqual(c.patch(f'{self.LIST}{sub.id}/', {'admin_permissions': ['nope']}, format='json').status_code, 400)
        entry = AuditLog.objects.get(action='admin.update')
        self.assertEqual(entry.metadata['before']['permissions'], ['manage_users'])

    def test_delete_admin(self):
        sub = make_user('a1@example.com', 'admin')
        self.assertEqual(self.as_user(self.super).delete(f'{self.LIST}{sub.id}/').status_code, 204)
        self.assertFalse(User.objects.filter(id=sub.id).exists())
        self.assertTrue(AuditLog.objects.filter(action='admin.delete').exists())

    def test_super_admins_and_self_are_protected(self):
        other_super = make_user('root2@example.com', 'admin', superuser=True)
        c = self.as_user(self.super)
        self.assertEqual(c.patch(f'{self.LIST}{other_super.id}/', {'is_active': False}, format='json').status_code, 403)
        self.assertEqual(c.delete(f'{self.LIST}{other_super.id}/').status_code, 403)
        self.assertEqual(c.delete(f'{self.LIST}{self.super.id}/').status_code, 403)

    def test_non_admin_accounts_are_not_reachable_here(self):
        self.assertEqual(self.as_user(self.super).delete(f'{self.LIST}{self.buyer.id}/').status_code, 404)
        self.assertTrue(User.objects.filter(id=self.buyer.id).exists())


class AuditLogTests(AdminTestBase):
    def test_requires_view_audit_log_permission(self):
        AuditLog.objects.create(action='x.y', actor_email='a@b.c')
        no = make_user('a1@example.com', 'admin', perms=['manage_users'])
        yes = make_user('a2@example.com', 'admin', perms=['view_audit_log'])
        self.assertEqual(self.as_user(no).get('/api/v1/users/admin/audit/').status_code, 403)
        resp = self.as_user(yes).get('/api/v1/users/admin/audit/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)

    def test_filtering(self):
        AuditLog.objects.create(action='user.deactivate', actor_id=1, target_type='user')
        AuditLog.objects.create(action='payment.release', actor_id=2, target_type='payment')
        c = self.as_user(self.super)
        self.assertEqual(c.get('/api/v1/users/admin/audit/?action=payment').json()['count'], 1)
        self.assertEqual(c.get('/api/v1/users/admin/audit/?actor_id=1').json()['count'], 1)

    def test_log_is_not_writable_by_admins(self):
        c = self.as_user(self.super)
        self.assertEqual(c.post('/api/v1/users/admin/audit/', {'action': 'x'}, format='json').status_code, 405)

    def test_internal_ingest_requires_service_token(self):
        body = {'actor_id': 5, 'actor_email': 'a@b.c', 'action': 'payment.release', 'target_type': 'payment', 'target_id': '9'}
        c = APIClient()
        self.assertIn(c.post('/api/v1/users/internal/audit/', body, format='json').status_code, (401, 403))
        ok = c.post('/api/v1/users/internal/audit/', body, format='json', HTTP_X_INTERNAL_TOKEN='test-token')
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertTrue(AuditLog.objects.filter(action='payment.release').exists())


class CatalogueAndSetupTests(AdminTestBase):
    def test_catalogue_lists_the_five_permissions(self):
        resp = self.as_user(self.super).get('/api/v1/users/admin/permissions/')
        self.assertEqual([p['id'] for p in resp.json()],
                         ['manage_users', 'manage_sellers', 'view_orders', 'manage_payments', 'view_audit_log'])
        self.assertEqual(self.as_user(self.buyer).get('/api/v1/users/admin/permissions/').status_code, 403)

    def test_setup_endpoint_needs_exact_secret(self):
        with mock.patch.dict(os.environ, {'ADMIN_SETUP_SECRET': 's3cret'}):
            c = APIClient()
            self.assertEqual(c.post('/api/v1/users/admin/setup/', {'email': 'buyer@example.com', 'secret': 'nope'}, format='json').status_code, 403)
            self.assertEqual(c.post('/api/v1/users/admin/setup/', {'email': 'buyer@example.com', 'secret': 's3cret'}, format='json').status_code, 200)
        self.buyer.refresh_from_db()
        self.assertEqual((self.buyer.role, self.buyer.is_superuser), ('admin', True))
        self.assertTrue(AuditLog.objects.filter(action='admin.setup').exists())
