from django.core.management.base import BaseCommand
import sys
import logging
from apps.notifications.models import Notification
from django.contrib.auth import get_user_model

try:
    from shared.core.events import consume_events
except ImportError:
    consume_events = None

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Consume RabbitMQ events for notifications'

    def handle(self, *args, **options):
        if not consume_events:
            self.stdout.write(self.style.ERROR("Could not import consume_events from shared.core.events"))
            return

        self.stdout.write(self.style.SUCCESS("Starting notification event consumer..."))

        def handle_event(ch, method, properties, body_dict):
            routing_key = method.routing_key
            self.stdout.write(f"Received event: {routing_key}")
            
            try:
                if routing_key == 'order.created':
                    buyer_id = body_dict.get('buyer_id')
                    order_id = body_dict.get('order_id')
                    if buyer_id and order_id:
                        Notification.objects.create(
                            recipient_id=buyer_id,
                            title=f"Order #{order_id} Received",
                            message=f"We have received your order #{order_id}. Awaiting payment."
                        )
                        self.stdout.write(self.style.SUCCESS(f"Notification created for order #{order_id}"))
                
                elif routing_key == 'order.payment.held':
                    buyer_id = body_dict.get('buyer_id')
                    store_id = body_dict.get('store_id')
                    order_id = body_dict.get('order_id')
                    
                    if buyer_id and order_id:
                        Notification.objects.create(
                            recipient_id=buyer_id,
                            title=f"Payment Successful (Order #{order_id})",
                            message=f"Your payment for order #{order_id} has been securely held in escrow. The seller will now ship your items."
                        )
                        self.stdout.write(self.style.SUCCESS(f"Notification sent for payment on order #{order_id}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing event {routing_key}: {e}"))

        try:
            consume_events(
                exchange='ubuntunow.events',
                queue_name='notification_queue',
                binding_keys=['order.#'],
                callback_func=handle_event
            )
        except Exception as e:
             self.stdout.write(self.style.ERROR(f"Failed to start consumer: {e}"))
