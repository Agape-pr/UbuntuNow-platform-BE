import os
import sys
import django
from django.conf import settings

# Setup Django environment for auth-service
auth_service_dir = "/Users/apple/Desktop/ubuntunow-platform/auth-service"
if auth_service_dir not in sys.path:
    sys.path.insert(0, auth_service_dir)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()

@override_settings(ALLOWED_HOSTS=['*'])
class ComprehensiveChallengerTestSuite(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="challenger_user@example.com",
            email="challenger_user@example.com",
            password="ChallengerPassword123!",
            role="buyer",
            first_name="Challenger",
            last_name="Tester"
        )
        self.token = str(AccessToken.for_user(self.user))

    # --- 1. Trailing Slash & URL Routing Tests ---

    def test_get_me_unauthenticated_noslash(self):
        """GET /api/v1/users/me without token -> must return 401, NOT 301/302."""
        response = self.client.get('/api/v1/users/me')
        self.assertEqual(response.status_code, 401, f"Expected 401, got {response.status_code}")
        self.assertNotIn('Location', response.headers)

    def test_get_me_unauthenticated_slash(self):
        """GET /api/v1/users/me/ without token -> must return 401, NOT 301/302."""
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, 401, f"Expected 401, got {response.status_code}")
        self.assertNotIn('Location', response.headers)

    def test_get_me_authenticated_noslash(self):
        """GET /api/v1/users/me with valid token -> must return 200 OK with user payload."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.get('/api/v1/users/me')
        self.assertEqual(response.status_code, 200, f"Expected 200, got {response.status_code}")
        data = response.json()
        self.assertEqual(data.get('email'), 'challenger_user@example.com')

    def test_get_me_authenticated_slash(self):
        """GET /api/v1/users/me/ with valid token -> must return 200 OK with user payload."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, 200, f"Expected 200, got {response.status_code}")
        data = response.json()
        self.assertEqual(data.get('email'), 'challenger_user@example.com')

    def test_patch_me_authenticated_noslash(self):
        """PATCH /api/v1/users/me with valid token -> must return 200 OK."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.patch('/api/v1/users/me', {'first_name': 'UpdatedName'}, format='json')
        self.assertEqual(response.status_code, 200, f"Expected 200, got {response.status_code}")
        self.assertEqual(response.json().get('first_name'), 'UpdatedName')

    def test_patch_me_authenticated_slash(self):
        """PATCH /api/v1/users/me/ with valid token -> must return 200 OK."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.patch('/api/v1/users/me/', {'first_name': 'UpdatedName2'}, format='json')
        self.assertEqual(response.status_code, 200, f"Expected 200, got {response.status_code}")
        self.assertEqual(response.json().get('first_name'), 'UpdatedName2')

    def test_post_me_authenticated_noslash_returns_405_not_301(self):
        """POST /api/v1/users/me -> method not allowed (405), NOT 301 redirect."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.post('/api/v1/users/me', {})
        self.assertEqual(response.status_code, 405, f"Expected 405, got {response.status_code}")

    def test_post_me_authenticated_slash_returns_405_not_301(self):
        """POST /api/v1/users/me/ -> method not allowed (405), NOT 301 redirect."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.post('/api/v1/users/me/', {})
        self.assertEqual(response.status_code, 405, f"Expected 405, got {response.status_code}")

    def test_invalid_token_returns_401_noslash(self):
        """GET /api/v1/users/me with invalid token -> 401 Unauthorized, NOT 301."""
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid_token_12345')
        response = self.client.get('/api/v1/users/me')
        self.assertEqual(response.status_code, 401, f"Expected 401, got {response.status_code}")

    # --- 2. CORS Implementation & Preflight Tests ---

    def test_cors_preflight_localhost_3000(self):
        """OPTIONS /api/v1/users/me from http://localhost:3000 -> Access-Control-Allow-Origin present."""
        response = self.client.options(
            '/api/v1/users/me',
            HTTP_ORIGIN='http://localhost:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:3000')

    def test_cors_preflight_localhost_5173(self):
        """OPTIONS /api/v1/users/me from http://localhost:5173 -> Access-Control-Allow-Origin present."""
        response = self.client.options(
            '/api/v1/users/me',
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    def test_cors_preflight_localhost_8000(self):
        """OPTIONS /api/v1/users/me from http://localhost:8000 -> Access-Control-Allow-Origin present."""
        response = self.client.options(
            '/api/v1/users/me',
            HTTP_ORIGIN='http://localhost:8000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:8000')

    def test_cors_preflight_127_0_0_1_3000(self):
        """OPTIONS /api/v1/users/me from http://127.0.0.1:3000 -> Access-Control-Allow-Origin present."""
        response = self.client.options(
            '/api/v1/users/me',
            HTTP_ORIGIN='http://127.0.0.1:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://127.0.0.1:3000')

    def test_cors_preflight_unallowed_origin(self):
        """OPTIONS /api/v1/users/me from http://evil-attacker.com -> Access-Control-Allow-Origin NOT set."""
        response = self.client.options(
            '/api/v1/users/me',
            HTTP_ORIGIN='http://evil-attacker.com',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertNotEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://evil-attacker.com')

    @override_settings(CORS_ALLOW_ALL_ORIGINS=True)
    def test_cors_allow_all_origins_setting(self):
        """CORS_ALLOW_ALL_ORIGINS=True allows any origin."""
        response = self.client.options(
            '/api/v1/users/me',
            HTTP_ORIGIN='http://random-origin.com',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization'
        )
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), '*')

if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    runner = DiscoverRunner(verbosity=2)
    failures = runner.run_tests(['test_empirical_routing_cors.ComprehensiveChallengerTestSuite'])
    sys.exit(bool(failures))


