import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(BASE_DIR, 'auth-service')
if AUTH_DIR not in sys.path:
    sys.path.insert(0, AUTH_DIR)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User
from apps.users.serializers import UserDetailSerializer
from rest_framework.test import APIRequestFactory

# Create user
user, created = User.objects.get_or_create(email="test2@example.com", defaults={"is_active": True})
if created:
    user.set_password("Test1234!")
    user.save()

# Test update via serializer
data = {
    "first_name": "Test Name",
    "address_line1": "123 Local St"
}
serializer = UserDetailSerializer(user, data=data, partial=True)
if serializer.is_valid():
    serializer.save()
    user.refresh_from_db()
    print("Serializer valid! Saved.")
    print("Updated address_line1:", getattr(user.profile, 'address_line1', None))
else:
    print("Serializer invalid:", serializer.errors)

