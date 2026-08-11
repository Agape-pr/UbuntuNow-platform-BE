import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User
from apps.users.serializers import UserDetailSerializer

user = User.objects.get(email="test2@example.com")
serializer = UserDetailSerializer(user)
print("Data:", serializer.data)
