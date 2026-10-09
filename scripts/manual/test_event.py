import sys
import os

# Set up paths so we can import shared
sys.path.append(os.path.abspath('.'))

from shared.core.events import publish_event

print("Publishing mock order.payment.held event...")
try:
    publish_event(
        exchange='ubuntunow.events',
        routing_key='order.payment.held',
        message_dict={
            'order_id': 999,
            'buyer_id': 1,
            'store_id': 1,
            'total_amount': '50.00',
            'status': 'shipped',
            'payment_status': 'held',
        }
    )
    print("✅ Event published successfully to RabbitMQ!")
except Exception as e:
    print(f"❌ Failed to publish: {e}")
