from .base import *
import dj_database_url

# Production defaults (do not import this for local dev).
DEBUG = False

if SECRET_KEY == "django-insecure-default-key":
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production.")

# Railway sets RAILWAY_PRIVATE_DOMAIN. If present, allow it automatically.
railway_hostname = os.environ.get("RAILWAY_PRIVATE_DOMAIN")
if railway_hostname and railway_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(railway_hostname)

# Must be set explicitly (or provided by Railway) in the environment.
if not ALLOWED_HOSTS:
    raise RuntimeError(
        "DJANGO_ALLOWED_HOSTS must be set in production (or RAILWAY_PRIVATE_DOMAIN must exist)."
    )

# Production database configuration - must respect the schema isolation from base.py
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600
    )
}

# Re-apply schema isolation because dj_database_url.config might overwrite it
schema = os.environ.get('DB_SCHEMA', 'public')
if 'postgresql' in DATABASES['default'].get('ENGINE', ''):
    DATABASES['default']['OPTIONS'] = {
        'options': f'-c search_path={schema}'
    }

#  hardening for HTTPS deployments.
# IMPORTANT: Set to False because the API Gateway communicates with this service via HTTP.
# SSL is handled at the Gateway edge (Vercel/Railway Public Domain).
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)

SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", default=True)

SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)

# X-Forwarded-Proto support (common behind proxies/load balancers)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# In production, be explicit about CORS rather than allowing all origins.
CORS_ALLOW_ALL_ORIGINS = False

# Trust Railway-hosted domain(s) for CSRF if you ever use cookie-based auth.
if railway_hostname:
    CSRF_TRUSTED_ORIGINS = [f"https://{railway_hostname}"]

# WhiteNoise static file storage (Railway-friendly) and Cloudinary for Media
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Enable WhiteNoise in production only.
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
