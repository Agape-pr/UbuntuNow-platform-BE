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


class PaymentStatusOwnershipTests(TestCase):
    """A payment's status is only visible to the buyer who owns the order (or a payments admin)."""

    def setUp(self):
        self.payment = Payment.objects.create(order_id=7, payment_method='momo', payment_amount=100, payment_status='completed')
        self.url = f'/api/v1/payments/payment/status/{self.payment.id}'

    def order_service(self, status_code):
        response = mock.Mock(status_code=status_code)
        return mock.patch('apps.payments.views.requests.get', return_value=response)

    def test_owner_can_see_it_and_the_buyers_own_token_is_used_for_the_check(self):
        with self.order_service(200) as get:
            resp = client_for(role='buyer', user_id=5).get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['payment_status'], 'completed')
        self.assertIn('/orders/orders/7/', get.call_args.args[0])
        self.assertTrue(get.call_args.kwargs['headers']['Authorization'].startswith('Bearer '))

    def test_other_buyers_get_404_not_403(self):
        for upstream in (404, 403):
            with self.order_service(upstream):
                self.assertEqual(client_for(role='buyer', user_id=6).get(self.url).status_code, 404, upstream)

    def test_unverifiable_requests_fail_closed(self):
        with self.order_service(500):
            self.assertEqual(client_for(role='buyer').get(self.url).status_code, 502)
        with mock.patch('apps.payments.views.requests.get', side_effect=ConnectionError('boom')):
            # ConnectionError here is not a requests exception, so make it one
            import requests
            with mock.patch('apps.payments.views.requests.get', side_effect=requests.ConnectionError('boom')):
                self.assertEqual(client_for(role='buyer').get(self.url).status_code, 502)

    def test_payments_admin_does_not_need_to_own_the_order(self):
        with mock.patch('apps.payments.views.requests.get') as get:
            resp = client_for(perms=['manage_payments']).get(self.url)
        self.assertEqual(resp.status_code, 200)
        get.assert_not_called()
        with self.order_service(404):
            self.assertEqual(client_for(perms=['view_orders']).get(self.url).status_code, 404)

    def test_anonymous_is_rejected(self):
        self.assertEqual(APIClient().get(self.url).status_code, 401)


class ErrorMessagesDoNotLeakTests(TestCase):
    def test_initiate_payment_hides_internal_errors(self):
        order = mock.Mock(status_code=200)
        order.raise_for_status.return_value = None
        order.json.return_value = {'total_amount': '100'}
        with mock.patch('apps.payments.views.requests.get', side_effect=RuntimeError("HTTPConnectionPool(host='10.0.0.7', port=8004)")):
            resp = client_for(role='buyer').post('/api/v1/payments/payment/create', {'order_id': 1, 'payment_method': 'momo', 'phone_number': '250780000000'}, format='json')
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn('10.0.0.7', resp.content.decode())
        self.assertNotIn('HTTPConnectionPool', resp.content.decode())

        with mock.patch('apps.payments.views.requests.get', return_value=order), \
             mock.patch.object(services.intouch_service, 'request_payment', side_effect=ValueError('INTOUCH_PARTNER_PASSWORD is not configured.')):
            resp = client_for(role='buyer').post('/api/v1/payments/payment/create', {'order_id': 2, 'payment_method': 'momo', 'phone_number': '250780000000'}, format='json')
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn('INTOUCH', resp.content.decode())

    def test_balance_error_is_generic(self):
        with mock.patch.object(services.intouch_service, 'get_balance', side_effect=RuntimeError('secret internals')):
            resp = client_for(perms=['manage_payments']).get('/api/v1/payments/payment/intouch-balance')
        self.assertEqual(resp.status_code, 502)
        self.assertNotIn('secret internals', resp.content.decode())


class IntouchWebhookSecretTests(TestCase):
    URL = '/api/v1/payments/payment/webhook/intouch/'

    def setUp(self):
        self.payment = Payment.objects.create(order_id=9, payment_method='momo', payment_amount=100,
                                              payment_status='pending', transaction_id='UBN9abc')
        self.body = {'jsonpayload': {'requesttransactionid': 'UBN9abc', 'status': 'Successfull', 'responsecode': '01'}}

    def post(self, query=''):
        with mock.patch('apps.payments.views.requests.patch'):
            return APIClient().post(self.URL + query, self.body, format='json')

    def test_without_a_configured_secret_callbacks_still_work(self):
        with self.settings(INTOUCH_WEBHOOK_SECRET=''):
            self.assertEqual(self.post().status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'completed')

    def test_with_a_secret_only_callbacks_carrying_it_are_accepted(self):
        with self.settings(INTOUCH_WEBHOOK_SECRET='s3cret'):
            for query in ('', '?token=wrong', '?token='):
                self.assertEqual(self.post(query).status_code, 403, query)
            self.payment.refresh_from_db()
            self.assertEqual(self.payment.payment_status, 'pending')
            self.assertEqual(self.post('?token=s3cret').status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'completed')

    def test_callback_url_given_to_intouchpay_carries_the_secret(self):
        svc = services.IntouchPayService()
        svc.callback_url = 'https://api.example.com/api/v1/payments/payment/webhook/intouch/'
        with self.settings(INTOUCH_WEBHOOK_SECRET='a b&c'):
            self.assertTrue(svc._callback_url_with_secret().endswith('/intouch/?token=a%20b%26c'))
            svc.callback_url += '?x=1'
            self.assertTrue(svc._callback_url_with_secret().endswith('?x=1&token=a%20b%26c'))
        with self.settings(INTOUCH_WEBHOOK_SECRET=''):
            self.assertEqual(svc._callback_url_with_secret(), svc.callback_url)
