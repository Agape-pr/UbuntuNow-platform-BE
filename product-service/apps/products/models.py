from django.db import models
from django.utils.text import slugify
from django.conf import settings


class Product(models.Model):
    store_id = models.IntegerField(db_index=True)
    category = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    in_stock = models.BooleanField(
        default=True,
        help_text="Does the seller currently hold this item in stock? "
                  "True = 'Ready for quick delivery'. "
                  "False = 'Confirm & deliver same day'."
    )
    variations = models.JSONField(default=dict, blank=True, null=True, help_text="e.g. {'colors': ['Red', 'Blue'], 'sizes': ['S', 'M']}")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)


    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='products/',null=True,
        blank=True)
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', '-uploaded_at']

    def __str__(self):
        return f"{self.product.name} Image"
