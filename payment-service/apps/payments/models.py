from django.db import models


class Payment(models.Model):
    class Method(models.TextChoices):
        MOMO = 'momo', 'MTN Mobile Money'
        AIRTEL = 'airtel', 'Airtel Money'
        # CARD = 'card', 'Credit/Debit Card'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed (Escrow Held)'
        RELEASED = 'released', 'Released to Seller'
        REFUNDED = 'refunded', 'Refunded to Buyer'
        FAILED = 'failed', 'Failed'

    order_id = models.IntegerField(unique=True)
    payment_method = models.CharField(max_length=20, choices=Method.choices)
    payment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.id} for Order {self.order_id}"
