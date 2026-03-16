"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

print("Starting Gunicorn... Loading Django settings...")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

try:
    application = get_wsgi_application()
    print("Django WSGI application loaded successfully!")
except Exception as e:
    import traceback
    print(f"FAILED TO LOAD WSGI: {e}")
    traceback.print_exc()
    raise
