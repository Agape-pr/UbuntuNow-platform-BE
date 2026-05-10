from django.db import models






class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SHIPPED = 'shipped', 'Shipped'
        READY_FOR_PICKUP = 'ready_for_pickup', 'Ready for Pickup'
        COMPLETED = 'completed', 'Completed'
        DISPUTED = 'disputed', 'Disputed'
        CANCELLED = 'cancelled', 'Cancelled'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        HELD = 'held', 'Held (Escrow)'
        RELEASED = 'released', 'Released'
        REFUNDED = 'refunded', 'Refunded'

    buyer_id = models.IntegerField(db_index=True)
    store_id = models.IntegerField(db_index=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - Buyer {self.buyer_id} - {self.status}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_id = models.IntegerField(db_index=True)
    product_name = models.CharField(max_length=255) # Snapshot in case product is deleted
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2) # Snapshot price
    selected_variations = models.JSONField(default=dict, blank=True, null=True, help_text="User selected options e.g. {'color': 'Red', 'size': 'M'}")

    @property
    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"
