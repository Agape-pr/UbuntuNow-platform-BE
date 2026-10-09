import os
import sys
import django
from django.conf import settings
from datetime import timedelta

if not settings.configured:
    settings.configure(
        SECRET_KEY="django-insecure-default-key",
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'rest_framework_simplejwt',
        ],
        SIMPLE_JWT={
            'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
        }
    )
django.setup()

from rest_framework_simplejwt.tokens import AccessToken
from shared.core.utils.auth import JWTStatelessAuthentication

token = AccessToken()
token['user_id'] = 1
token['role'] = 'buyer'
raw_token = str(token)

auth = JWTStatelessAuthentication()
try:
    validated_token = auth.get_validated_token(raw_token.encode('utf-8'))
    user = auth.get_user(validated_token)
    print("SUCCESS: user_id =", user.id)
except Exception as e:
    print("FAILED:", type(e).__name__, str(e))
