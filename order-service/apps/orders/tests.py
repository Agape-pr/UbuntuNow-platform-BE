from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .models import Order

URL = '/api/v1/orders/admin/orders/'


def client_for(role='admin', perms=None, superuser=False, user_id=1):
    token = AccessToken()
    token['user_id'] = user_id
    token['role'] = role
    token['is_superuser'] = superuser
    token['admin_permissions'] = perms or []
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


class AdminOrderListTests(TestCase):
    def setUp(self):
        self.o1 = Order.objects.create(buyer_id=7, store_id=1, total_amount=1000, status='pending')
        self.o2 = Order.objects.create(buyer_id=8, store_id=2, total_amount=2000, status='confirmed', payment_status='paid')

    def test_requires_view_orders_permission(self):
        self.assertEqual(client_for(perms=['view_orders']).get(URL).status_code, 200)
        self.assertEqual(client_for(superuser=True).get(URL).status_code, 200)
        self.assertEqual(client_for(perms=['manage_users']).get(URL).status_code, 403)
        self.assertEqual(client_for(perms=[]).get(URL).status_code, 403)

    def test_non_admins_and_anonymous_are_blocked(self):
        self.assertEqual(client_for(role='buyer', perms=['view_orders']).get(URL).status_code, 403)
        self.assertEqual(client_for(role='seller', perms=['view_orders'], superuser=True).get(URL).status_code, 403)
        self.assertEqual(APIClient().get(URL).status_code, 401)

    def test_lists_all_orders_paginated_with_buyer(self):
        data = client_for(perms=['view_orders']).get(URL).json()
        self.assertEqual(data['count'], 2)
        self.assertEqual({o['buyer_id'] for o in data['results']}, {7, 8})

    def test_filters(self):
        c = client_for(perms=['view_orders'])
        self.assertEqual(c.get(URL + '?status=confirmed').json()['count'], 1)
        self.assertEqual(c.get(URL + '?payment_status=paid').json()['count'], 1)
        self.assertEqual(c.get(URL + '?store_id=1').json()['count'], 1)
        self.assertEqual(c.get(URL + f'?search=%23{self.o1.id}').json()['count'], 1)

    def test_is_read_only(self):
        c = client_for(superuser=True)
        self.assertEqual(c.post(URL, {}, format='json').status_code, 405)
        self.assertEqual(c.delete(f'{URL}{self.o1.id}/').status_code, 405)
        self.assertEqual(c.patch(f'{URL}{self.o1.id}/', {'status': 'cancelled'}, format='json').status_code, 405)


# ───────────────────────── checkout, ownership, internal endpoints ─────────────────────────
import os
from unittest import mock

from .models import Order, OrderItem


def user_client(role='buyer', user_id=1, store_id=None):
    token = AccessToken()
    token['user_id'] = user_id
    token['role'] = role
    if store_id:
        token['store_id'] = store_id
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def product(pid, store_id, price='1000.00', stock=10, name=None):
    return {'id': pid, 'name': name or f'Item {pid}', 'price': price, 'stock_quantity': stock, 'store_id': store_id}


def fake_product_service(products):
    def get(url, **kwargs):
        pid = int(url.rstrip('/').split('/')[-1])
        found = products.get(pid)
        resp = mock.Mock(status_code=200 if found else 404)
        resp.json.return_value = found
        return resp
    return get


class CheckoutTests(TestCase):
    URL = '/api/v1/orders/checkout/'

    def setUp(self):
        env = mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': 'tok', 'PRODUCT_SERVICE_URL': 'http://products'})
        env.start()
        self.addCleanup(env.stop)

    def checkout(self, items, products, **client_kwargs):
        with mock.patch('apps.orders.views.requests.get', side_effect=fake_product_service(products)), \
             mock.patch('apps.orders.views.requests.patch') as patch, \
             mock.patch('shared.core.events.publish_event') as event:
            resp = user_client(**client_kwargs).post(self.URL, {'items': items, 'delivery_address': {'city': 'Kigali'}}, format='json')
        return resp, patch, event

    def test_price_comes_from_the_product_service_not_the_client(self):
        resp, _, _ = self.checkout([{'product_id': 1, 'quantity': 3, 'price': '1'}], {1: product(1, store_id=5, price='2500.00')}, user_id=9)
        self.assertEqual(resp.status_code, 201, resp.content)
        order = Order.objects.get()
        self.assertEqual((order.buyer_id, order.store_id, float(order.total_amount)), (9, 5, 7500.0))
        self.assertEqual(float(OrderItem.objects.get().price), 2500.0)

    def test_one_order_per_store(self):
        products = {1: product(1, store_id=5), 2: product(2, store_id=6), 3: product(3, store_id=5)}
        resp, _, event = self.checkout([{'product_id': i, 'quantity': 1} for i in (1, 2, 3)], products)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(sorted(Order.objects.values_list('store_id', flat=True)), [5, 6])
        self.assertEqual(event.call_count, 2)

    def test_stock_is_deducted_through_the_authenticated_internal_endpoint(self):
        _, patch, _ = self.checkout([{'product_id': 1, 'quantity': 4}], {1: product(1, store_id=5, stock=10)})
        patch.assert_called_once()
        self.assertTrue(patch.call_args.args[0].endswith('/api/v1/products/internal/stock/1/'))
        self.assertEqual(patch.call_args.kwargs['json'], {'stock_quantity': 6})
        self.assertEqual(patch.call_args.kwargs['headers']['X-Internal-Token'], 'tok')

    def test_insufficient_stock_creates_nothing(self):
        resp, patch, _ = self.checkout([{'product_id': 1, 'quantity': 11}], {1: product(1, store_id=5, stock=10)})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        patch.assert_not_called()

    def test_unknown_product_is_rejected(self):
        resp, _, _ = self.checkout([{'product_id': 99, 'quantity': 1}], {})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_invalid_payload_and_anonymous_requests(self):
        resp, _, _ = self.checkout([{'product_id': 1, 'quantity': 0}], {1: product(1, store_id=5)})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(APIClient().post(self.URL, {'items': []}, format='json').status_code, 401)

    def test_the_old_free_mock_payment_shortcut_is_gone(self):
        order = Order.objects.create(buyer_id=1, store_id=5, total_amount=1000)
        for url in (f'/api/v1/orders/{order.id}/mock-payment/', f'/api/v1/orders/orders/{order.id}/mock-payment/'):
            self.assertEqual(user_client(user_id=1).post(url).status_code, 404, url)
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), ('pending', 'pending'))


class OrderOwnershipTests(TestCase):
    def setUp(self):
        self.mine = Order.objects.create(buyer_id=1, store_id=5, total_amount=100)
        self.theirs = Order.objects.create(buyer_id=2, store_id=5, total_amount=200)
        self.other_store = Order.objects.create(buyer_id=2, store_id=6, total_amount=300)

    def ids(self, resp):
        data = resp.json()
        return sorted(o['id'] for o in (data['results'] if isinstance(data, dict) else data))

    def test_buyers_only_see_their_own_orders(self):
        c = user_client(user_id=1)
        self.assertEqual(self.ids(c.get('/api/v1/orders/orders/')), [self.mine.id])
        self.assertEqual(c.get(f'/api/v1/orders/orders/{self.theirs.id}/').status_code, 404)

    def test_sellers_only_see_and_update_their_own_stores_orders(self):
        c = user_client(role='seller', user_id=50, store_id=5)
        self.assertEqual(self.ids(c.get('/api/v1/orders/seller/orders/')), sorted([self.mine.id, self.theirs.id]))
        self.assertEqual(c.get(f'/api/v1/orders/seller/orders/{self.other_store.id}/').status_code, 404)
        url = f'/api/v1/orders/seller/orders/{self.mine.id}/update-status/'
        self.assertEqual(c.post(url, {'status': 'shipped'}, format='json').status_code, 200)
        self.assertEqual(c.post(url, {'status': 'completed'}, format='json').status_code, 400)
        self.assertEqual(c.post(f'/api/v1/orders/seller/orders/{self.other_store.id}/update-status/', {'status': 'shipped'}, format='json').status_code, 404)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, 'shipped')

    def test_a_buyer_cannot_use_the_seller_endpoints(self):
        c = user_client(role='buyer', user_id=1)
        self.assertEqual(self.ids(c.get('/api/v1/orders/seller/orders/')), [])
        url = f'/api/v1/orders/seller/orders/{self.mine.id}/update-status/'
        self.assertEqual(c.post(url, {'status': 'shipped'}, format='json').status_code, 404)

    def test_confirm_receipt_only_after_shipping_and_only_by_the_buyer(self):
        url = f'/api/v1/orders/orders/{self.mine.id}/confirm-receipt/'
        self.assertEqual(user_client(user_id=1).post(url).status_code, 400)
        self.assertEqual(user_client(user_id=2).post(url).status_code, 404)
        self.mine.status = 'shipped'; self.mine.save()
        self.assertEqual(user_client(user_id=1).post(url).status_code, 200)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, 'completed')


class InternalEndpointTests(TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': 'tok'})
        env.start()
        self.addCleanup(env.stop)
        self.order = Order.objects.create(buyer_id=1, store_id=5, total_amount=100)
        self.url = f'/api/v1/orders/internal/{self.order.id}/'
        self.h = {'HTTP_X_INTERNAL_TOKEN': 'tok'}

    def test_a_token_is_required(self):
        c = APIClient()
        self.assertIn(c.get(self.url).status_code, (401, 403))
        self.assertIn(c.get(self.url, HTTP_X_INTERNAL_TOKEN='wrong').status_code, (401, 403))
        self.assertIn(c.patch(self.url + 'update-payment/', {'payment_status': 'paid'}, format='json').status_code, (401, 403))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'pending')
        self.assertEqual(c.get(self.url, **self.h).status_code, 200)

    def test_it_exposes_nothing_beyond_retrieve_and_update_payment(self):
        c = APIClient()
        self.assertEqual(c.get('/api/v1/orders/internal/', **self.h).status_code, 404)
        self.assertEqual(c.delete(self.url, **self.h).status_code, 405)
        self.assertEqual(c.put(self.url, {}, format='json', **self.h).status_code, 405)
        self.assertTrue(Order.objects.filter(id=self.order.id).exists())

    def test_update_payment_validates_and_announces_a_new_payment_once(self):
        c = APIClient()
        url = self.url + 'update-payment/'
        self.assertEqual(c.patch(url, {'payment_status': 'bogus'}, format='json', **self.h).status_code, 400)
        self.assertEqual(c.patch(url, {'status': 'hacked'}, format='json', **self.h).status_code, 400)
        with mock.patch('shared.core.events.publish_event') as event:
            body = {'payment_status': 'paid', 'status': 'confirmed'}
            self.assertEqual(c.patch(url, body, format='json', **self.h).status_code, 200)
            self.assertEqual(c.patch(url, body, format='json', **self.h).status_code, 200)  # webhook retry
        self.assertEqual(event.call_count, 1)
        self.assertEqual(event.call_args.kwargs['routing_key'], 'order.payment.held')
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ('confirmed', 'paid'))
        self.assertEqual(c.patch('/api/v1/orders/internal/99999/update-payment/', {'payment_status': 'paid'}, format='json', **self.h).status_code, 404)
