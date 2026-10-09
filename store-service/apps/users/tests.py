import os
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .models import Store


def user_client(user_id, role='seller'):
    token = AccessToken()
    token['user_id'] = user_id
    token['role'] = role
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


class InternalStoreEndpointTests(TestCase):
    """Internal endpoints hand out payout numbers and create stores, so they need the service token."""

    def setUp(self):
        env = mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': 'tok'})
        env.start()
        self.addCleanup(env.stop)
        self.store = Store.objects.create(user_id=9, store_name='Test Shop', payout_phone_number='250780000000')
        self.h = {'HTTP_X_INTERNAL_TOKEN': 'tok'}

    def test_reads_need_the_token(self):
        for path in (f'/api/v1/users/internal/stores/{self.store.user_id}/', f'/api/v1/users/internal/stores/by-id/{self.store.id}/'):
            c = APIClient()
            self.assertIn(c.get(path).status_code, (401, 403), path)
            self.assertIn(c.get(path, HTTP_X_INTERNAL_TOKEN='wrong').status_code, (401, 403), path)
            ok = c.get(path, **self.h)
            self.assertEqual(ok.status_code, 200, path)
            self.assertEqual(ok.json()['payout_phone_number'], '250780000000')

    def test_creating_a_store_needs_the_token(self):
        body = {'user_id': 99, 'store_name': 'Evil Shop'}
        self.assertIn(APIClient().post('/api/v1/users/internal/stores/', body, format='json').status_code, (401, 403))
        self.assertFalse(Store.objects.filter(user_id=99).exists())
        self.assertEqual(APIClient().post('/api/v1/users/internal/stores/', body, format='json', **self.h).status_code, 201)
        self.assertTrue(Store.objects.filter(user_id=99).exists())

    def test_service_token_not_configured_means_closed(self):
        with mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': ''}):
            resp = APIClient().get(f'/api/v1/users/internal/stores/{self.store.user_id}/', HTTP_X_INTERNAL_TOKEN='')
        self.assertIn(resp.status_code, (401, 403))


class PublicAndOwnStoreTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(user_id=9, store_name='Test Shop', payout_phone_number='250780000000')

    def test_public_page_works_without_login_and_hides_the_payout_number(self):
        with mock.patch('requests.get', side_effect=ConnectionError):
            resp = APIClient().get(f'/api/v1/users/store/{self.store.slug}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['store_name'], 'Test Shop')
        self.assertNotIn('payout_phone_number', resp.json())
        self.assertNotIn('250780000000', resp.content.decode())

    def test_sellers_edit_only_their_own_store(self):
        other = Store.objects.create(user_id=10, store_name='Other Shop')
        resp = user_client(9).patch('/api/v1/users/store/me/', {'store_name': 'Renamed'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.store.refresh_from_db(); other.refresh_from_db()
        self.assertEqual((self.store.store_name, other.store_name), ('Renamed', 'Other Shop'))
        self.assertEqual(user_client(404).patch('/api/v1/users/store/me/', {'store_name': 'x'}, format='json').status_code, 404)
        self.assertEqual(APIClient().patch('/api/v1/users/store/me/', {'store_name': 'x'}, format='json').status_code, 401)
