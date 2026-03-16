import pika
import json
import os
import logging

logger = logging.getLogger(__name__)

def get_connection():
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    params = pika.URLParameters(url)
    return pika.BlockingConnection(params)

def publish_event(exchange, routing_key, message_dict):
    """
    Publish an event to RabbitMQ using a topic exchange.
    """
    try:
        connection = get_connection()
        channel = connection.channel()
        channel.exchange_declare(exchange=exchange, exchange_type='topic', durable=True)
        
        message_body = json.dumps(message_dict)
        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=message_body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        connection.close()
        logger.info(f"Published event '{routing_key}' to '{exchange}'")
    except Exception as e:
        logger.error(f"Failed to publish event: {e}")

def consume_events(exchange, queue_name, binding_keys, callback_func):
    """
    Consume events from RabbitMQ.
    callback_func signature: def callback_func(ch, method, properties, body_dict)
    """
    try:
        connection = get_connection()
        channel = connection.channel()
        channel.exchange_declare(exchange=exchange, exchange_type='topic', durable=True)
        
        result = channel.queue_declare(queue=queue_name, durable=True)
        
        for key in binding_keys:
            channel.queue_bind(exchange=exchange, queue=queue_name, routing_key=key)
            
        def wrapper(ch, method, properties, body):
            body_dict = json.loads(body.decode('utf-8'))
            callback_func(ch, method, properties, body_dict)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_consume(queue=queue_name, on_message_callback=wrapper)
        logger.info(f"Started consuming events from '{queue_name}'...")
        channel.start_consuming()
    except Exception as e:
        logger.error(f"Failed to consume events: {e}")
