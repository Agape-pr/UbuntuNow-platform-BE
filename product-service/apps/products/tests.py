from django.test import TestCase, override_settings
from rest_framework.test import APIClient

class ProductServiceCORSTests(TestCase):
    def test_cors_options_preflight_localhost_3000(self):
        """Verify OPTIONS request from localhost:3000 returns allowed origin header."""
        client = APIClient()
        response = client.options(
            '/api/v1/products/',
            HTTP_ORIGIN='http://localhost:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:3000')

    def test_cors_options_preflight_localhost_5173(self):
        """Verify OPTIONS request from localhost:5173 returns allowed origin header."""
        client = APIClient()
        response = client.options(
            '/api/v1/products/',
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    @override_settings(CORS_ALLOWED_ORIGINS=['http://custom-frontend.example.com'])
    def test_cors_custom_origin_override(self):
        """Verify custom CORS_ALLOWED_ORIGINS dynamically allows configured origin."""
        client = APIClient()
        response = client.options(
            '/api/v1/products/',
            HTTP_ORIGIN='http://custom-frontend.example.com',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://custom-frontend.example.com')


# ───────────────────────── stock endpoint, ownership, public listing ─────────────────────────
import os
from unittest import mock

from rest_framework_simplejwt.tokens import AccessToken

from .models import Product


def seller_client(user_id=1, store_id=5, role='seller'):
    token = AccessToken()
    token['user_id'] = user_id
    token['role'] = role
    if store_id:
        token['store_id'] = store_id
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


class InternalStockEndpointTests(TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': 'tok'})
        env.start()
        self.addCleanup(env.stop)
        self.product = Product.objects.create(store_id=5, category='shoes', name='Boot', price=100, stock_quantity=5)
        self.url = f'/api/v1/products/internal/stock/{self.product.id}/'

    def test_requires_the_service_token(self):
        c = APIClient()
        self.assertIn(c.patch(self.url, {'stock_quantity': 0}, format='json').status_code, (401, 403))
        self.assertIn(c.patch(self.url, {'stock_quantity': 0}, format='json', HTTP_X_INTERNAL_TOKEN='x').status_code, (401, 403))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)
        ok = c.patch(self.url, {'stock_quantity': 3}, format='json', HTTP_X_INTERNAL_TOKEN='tok')
        self.assertEqual(ok.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

    def test_a_seller_token_is_not_enough(self):
        resp = seller_client().patch(self.url, {'stock_quantity': 999}, format='json')
        self.assertIn(resp.status_code, (401, 403))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)


class SellerProductOwnershipTests(TestCase):
    URL = '/api/v1/products/seller/products/'

    def setUp(self):
        self.mine = Product.objects.create(store_id=5, category='shoes', name='Mine', price=100, stock_quantity=1)
        self.theirs = Product.objects.create(store_id=6, category='shoes', name='Theirs', price=100, stock_quantity=1)

    def names(self, resp):
        data = resp.json()
        return sorted(p['name'] for p in (data['results'] if isinstance(data, dict) else data))

    def test_a_seller_only_sees_their_own_products(self):
        self.assertEqual(self.names(seller_client(store_id=5).get(self.URL)), ['Mine'])

    def test_a_seller_cannot_touch_another_stores_product(self):
        c = seller_client(store_id=5)
        self.assertEqual(c.get(f'{self.URL}{self.theirs.id}/').status_code, 404)
        self.assertEqual(c.patch(f'{self.URL}{self.theirs.id}/', {'name': 'Hacked'}, format='json').status_code, 404)
        self.assertEqual(c.delete(f'{self.URL}{self.theirs.id}/').status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.name, 'Theirs')

    def test_buyers_and_anonymous_users_cannot_use_the_seller_endpoints(self):
        self.assertIn(seller_client(role='buyer').get(self.URL).status_code, (401, 403))
        self.assertIn(APIClient().get(self.URL).status_code, (401, 403))

    def test_products_created_by_a_seller_belong_to_their_store(self):
        resp = seller_client(store_id=5).post(self.URL, {
            'category': 'shoes', 'name': 'New', 'price': '10.00', 'stock_quantity': 2, 'store_id': 6}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Product.objects.get(name='New').store_id, 5)  # a client-sent store_id is ignored


class PublicProductListTests(TestCase):
    def test_inactive_products_are_hidden_and_no_login_is_needed(self):
        Product.objects.create(store_id=5, category='a', name='Visible', price=1, stock_quantity=1)
        Product.objects.create(store_id=5, category='a', name='Hidden', price=1, stock_quantity=1, is_active=False)
        resp = APIClient().get('/api/v1/products/products/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        names = [p['name'] for p in (data['results'] if isinstance(data, dict) else data)]
        self.assertEqual(names, ['Visible'])
