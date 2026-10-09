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
