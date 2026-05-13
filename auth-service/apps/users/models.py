from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', _('Admin')
        SELLER = 'seller', _('Seller')
        BUYER = 'buyer', _('Buyer')

    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.BUYER,
    )
    admin_permissions = models.JSONField(
        default=list, 
        blank=True,
        help_text=_("List of permissions for sub-admins, e.g. ['manage_buyers', 'manage_sellers']")
    )

    
    
    REQUIRED_FIELDS = ['email', 'role']

    def __str__(self):
        return self.username

    def is_seller(self):
        return self.role == self.Role.SELLER

    def is_buyer(self):
        return self.role == self.Role.BUYER


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='Rwanda')

    def __str__(self):
        return f"Profile for {self.user.email}"
