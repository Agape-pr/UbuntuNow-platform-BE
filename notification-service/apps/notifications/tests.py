import os
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from apps.notifications.management.commands import consume_notifications as consumer
from apps.notifications.models import Notification


class ConsumerTests(TestCase):
    """The event handler registered by the consume_notifications command."""

    def setUp(self):
        env = mock.patch.dict(os.environ, {'INTERNAL_SERVICE_TOKEN': 'tok', 'STORE_SERVICE_URL': 'http://stores'})
        env.start()
        self.addCleanup(env.stop)
        captured = {}
        with mock.patch.object(consumer, 'consume_events', lambda **kw: captured.update(cb=kw['callback_func'])):
            consumer.Command().handle()
        self.handle = captured['cb']

    def emit(self, routing_key, body):
        self.handle(None, SimpleNamespace(routing_key=routing_key), None, body)

    def test_order_created_notifies_the_buyer(self):
        self.emit('order.created', {'order_id': 4, 'buyer_id': 7})
        n = Notification.objects.get()
        self.assertEqual(n.recipient_id, 7)
        self.assertIn('#4', n.title)

    def test_payment_notifies_buyer_and_the_seller_found_through_the_internal_store_lookup(self):
        store = mock.Mock(status_code=200)
        store.json.return_value = {'id': 3, 'user_id': 9}
        with mock.patch('requests.get', return_value=store) as get:
            self.emit('order.payment.held', {'order_id': 4, 'buyer_id': 7, 'store_id': 3})
        self.assertEqual(sorted(Notification.objects.values_list('recipient_id', flat=True)), [7, 9])
        self.assertTrue(get.call_args.args[0].endswith('/api/v1/users/internal/stores/by-id/3/'))
        self.assertEqual(get.call_args.kwargs['headers']['X-Internal-Token'], 'tok')

    def test_buyer_is_still_notified_when_the_store_lookup_fails(self):
        with mock.patch('requests.get', side_effect=ConnectionError):
            self.emit('order.payment.held', {'order_id': 4, 'buyer_id': 7, 'store_id': 3})
        self.assertEqual(list(Notification.objects.values_list('recipient_id', flat=True)), [7])

    def test_events_with_missing_fields_or_unknown_keys_are_ignored(self):
        self.emit('order.created', {})
        self.emit('order.something.else', {'order_id': 1, 'buyer_id': 1})
        self.assertEqual(Notification.objects.count(), 0)
