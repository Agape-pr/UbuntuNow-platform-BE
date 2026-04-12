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


