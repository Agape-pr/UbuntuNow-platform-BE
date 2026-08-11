import os
import sys
import django

# Setup Django environment for product-service
product_service_dir = "/Users/apple/Desktop/ubuntunow-platform/product-service"
if product_service_dir not in sys.path:
    sys.path.insert(0, product_service_dir)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

@override_settings(ALLOWED_HOSTS=['*'])
class ProductServiceChallengerTestSuite(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_cors_preflight_localhost_3000(self):
        response = self.client.options(
            '/api/v1/products/',
            HTTP_ORIGIN='http://localhost:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:3000')

    def test_cors_preflight_localhost_5173(self):
        response = self.client.options(
            '/api/v1/products/',
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    def test_cors_preflight_127_0_0_1_3000(self):
        response = self.client.options(
            '/api/v1/products/',
            HTTP_ORIGIN='http://127.0.0.1:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://127.0.0.1:3000')

    def test_cors_preflight_unallowed_origin(self):
        response = self.client.options(
            '/api/v1/products/',
            HTTP_ORIGIN='http://unauthorized-domain.com',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization'
        )
        self.assertNotEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://unauthorized-domain.com')

if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    runner = DiscoverRunner(verbosity=2)
    failures = runner.run_tests(['test_product_service_cors.ProductServiceChallengerTestSuite'])
    sys.exit(bool(failures))
