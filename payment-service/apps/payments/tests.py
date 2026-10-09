import os
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from . import services
from .models import Payment


def client_for(role='admin', perms=None, superuser=False, user_id=1):
    token = AccessToken()
    token['user_id'] = user_id
    token['role'] = role
    token['email'] = 'admin@example.com'
    token['is_superuser'] = superuser
    token['admin_permissions'] = perms or []
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


ADMIN_URLS = [
    ('get', '/api/v1/payments/payment/releasable'),
    ('get', '/api/v1/payments/payment/intouch-balance'),
    ('get', '/api/v1/payments/payment/admin/list'),
]


class AdminPaymentPermissionTests(TestCase):
    def test_only_manage_payments_admins_get_through(self):
        for method, url in ADMIN_URLS:
            with mock.patch.object(services.intouch_service, 'get_balance', return_value={'success': True, 'balance': '10'}):
                ok = getattr(client_for(perms=['manage_payments']), method)(url)
                sup = getattr(client_for(superuser=True), method)(url)
            self.assertEqual(ok.status_code, 200, url)
            self.assertEqual(sup.status_code, 200, url)
            self.assertEqual(getattr(client_for(perms=['view_orders']), method)(url).status_code, 403, url)
            self.assertEqual(getattr(client_for(role='seller', perms=['manage_payments']), method)(url).status_code, 403, url)
            self.assertEqual(getattr(client_for(role='buyer', superuser=True), method)(url).status_code, 403, url)
            self.assertEqual(getattr(APIClient(), method)(url).status_code, 401, url)

    def test_release_is_blocked_without_permission(self):
        p = Payment.objects.create(order_id=1, payment_method='momo', payment_amount=100, payment_status='completed')
        resp = client_for(perms=['view_orders']).post('/api/v1/payments/payment/release', {'payment_id': p.id}, format='json')
        self.assertEqual(resp.status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.payment_status, 'completed')

    def test_admin_list_filters_by_status(self):
        Payment.objects.create(order_id=1, payment_method='momo', payment_amount=100, payment_status='completed', transaction_id='a')
        Payment.objects.create(order_id=2, payment_method='momo', payment_amount=100, payment_status='failed', transaction_id='b')
        data = client_for(superuser=True).get('/api/v1/payments/payment/admin/list?status=failed').json()
        self.assertEqual(data['count'], 1)


class ReleaseFlowTests(TestCase):
    """The escrow release still works for a permitted admin and leaves an audit entry."""

    def setUp(self):
        env = mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': 'tok'})
        env.start()
        self.addCleanup(env.stop)
        self.payment = Payment.objects.create(order_id=5, payment_method='momo', payment_amount=5000, payment_status='completed')

    def _get(self, url, **kwargs):
        resp = mock.Mock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.return_value = {'store_id': 3} if '/orders/internal/' in url else {'payout_phone_number': '250780000000'}
        return resp

    def test_release_pays_out_and_audits(self):
        with mock.patch('apps.payments.views.requests.get', side_effect=self._get) as get, \
             mock.patch.object(services.intouch_service, 'send_deposit',
                               return_value={'success': True, 'transactionid': 'T1', 'referenceno': 'R1'}) as deposit, \
             mock.patch('shared.core.utils.audit_client.requests.post') as audit_post:
            resp = client_for(perms=['manage_payments']).post(
                '/api/v1/payments/payment/release', {'payment_id': self.payment.id}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(deposit.call_args.kwargs['mobile_phone'], '250780000000')
        self.assertTrue(all(c.kwargs['headers'].get('X-Internal-Token') == 'tok' for c in get.call_args_list))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'released')

        body = audit_post.call_args.kwargs['json']
        self.assertEqual((body['action'], body['target_id'], body['actor_email']), ('payment.release', str(self.payment.id), 'admin@example.com'))
        self.assertEqual(audit_post.call_args.kwargs['headers']['X-Internal-Token'], 'tok')

    def test_failed_payout_is_audited_and_not_released(self):
        with mock.patch('apps.payments.views.requests.get', side_effect=self._get), \
             mock.patch.object(services.intouch_service, 'send_deposit', return_value={'success': False, 'message': 'nope'}), \
             mock.patch('shared.core.utils.audit_client.requests.post') as audit_post:
            resp = client_for(superuser=True).post('/api/v1/payments/payment/release', {'payment_id': self.payment.id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'completed')
        self.assertEqual(audit_post.call_args.kwargs['json']['action'], 'payment.release.failed')

    def test_audit_outage_never_blocks_a_payout(self):
        with mock.patch('apps.payments.views.requests.get', side_effect=self._get), \
             mock.patch.object(services.intouch_service, 'send_deposit', return_value={'success': True, 'transactionid': 'T'}), \
             mock.patch('shared.core.utils.audit_client.requests.post', side_effect=ConnectionError):
            resp = client_for(superuser=True).post('/api/v1/payments/payment/release', {'payment_id': self.payment.id}, format='json')
        self.assertEqual(resp.status_code, 200)
