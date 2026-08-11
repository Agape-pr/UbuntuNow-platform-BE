from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
import os

User = get_user_model()

class UserMeEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser@example.com",
            email="testuser@example.com",
            password="TestPassword123!",
            role="buyer",
            first_name="Test",
            last_name="User"
        )
        self.token = str(AccessToken.for_user(self.user))

    def test_me_without_trailing_slash_returns_401_or_200_not_301(self):
        """Verify GET /api/v1/users/me does NOT return HTTP 301 redirect."""
        response = self.client.get('/api/v1/users/me')
        self.assertNotEqual(response.status_code, 301)
        self.assertEqual(response.status_code, 401)

    def test_me_with_trailing_slash_returns_401_not_301(self):
        """Verify GET /api/v1/users/me/ returns 401 when unauthenticated."""
        response = self.client.get('/api/v1/users/me/')
        self.assertNotEqual(response.status_code, 301)
        self.assertEqual(response.status_code, 401)

    def test_me_authenticated_without_trailing_slash(self):
        """Verify GET /api/v1/users/me with Bearer token returns 200 OK and user data."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.get('/api/v1/users/me')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['email'], 'testuser@example.com')

    def test_me_authenticated_with_trailing_slash(self):
        """Verify GET /api/v1/users/me/ with Bearer token returns 200 OK and user data."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['email'], 'testuser@example.com')

class CORSSettingsTests(TestCase):
    def test_cors_options_preflight_allowed_origin(self):
        """Verify OPTIONS request from localhost:3000 returns allowed origin header."""
        client = APIClient()
        response = client.options(
            '/api/v1/users/me',
            HTTP_ORIGIN='http://localhost:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:3000')

    def test_cors_options_preflight_5173(self):
        """Verify OPTIONS request from localhost:5173 returns allowed origin header."""
        client = APIClient()
        response = client.options(
            '/api/v1/users/me',
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
            '/api/v1/users/me',
            HTTP_ORIGIN='http://custom-frontend.example.com',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://custom-frontend.example.com')

