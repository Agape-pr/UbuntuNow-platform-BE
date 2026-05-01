from django.core.management.base import BaseCommand
import sys
import logging
from apps.products.models import Product
from django.db import transaction

try:
    from shared.core.events import consume_events
except ImportError:
    consume_events = None

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Consume RabbitMQ events for product stock management'

    def handle(self, *args, **options):
        if not consume_events:
            self.stdout.write(self.style.ERROR("Could not import consume_events from shared.core.events"))
            return

        self.stdout.write(self.style.SUCCESS("Starting product stock event consumer..."))

        def handle_event(ch, method, properties, body_dict):
            routing_key = method.routing_key
            self.stdout.write(f"Received event: {routing_key}")
            
            try:
                if routing_key == 'order.created':
                    order_id = body_dict.get('order_id')
                    # Because we don't have individual item quantities in the top-level 'order.created' event payload,
                    # we should ideally fetch the items or have them in the payload.
                    # Wait! The current order.created payload doesn't contain items!
                    pass
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing event {routing_key}: {e}"))

        try:
            consume_events(
                exchange='ubuntunow.events',
                queue_name='product_stock_queue',
                binding_keys=['order.#'],
                callback_func=handle_event
            )
        except Exception as e:
             self.stdout.write(self.style.ERROR(f"Failed to start consumer: {e}"))
