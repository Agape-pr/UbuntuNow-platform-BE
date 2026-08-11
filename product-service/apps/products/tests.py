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
