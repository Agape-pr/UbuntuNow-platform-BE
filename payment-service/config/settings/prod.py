from .base import *
import dj_database_url

# Production defaults (do not import this for local dev).
DEBUG = False

if SECRET_KEY == "django-insecure-default-key":
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production.")

# Render sets RENDER_EXTERNAL_HOSTNAME. If present, allow it automatically.
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)

# Must be set explicitly (or provided by Render) in the environment.
if not ALLOWED_HOSTS:
    raise RuntimeError(
        "DJANGO_ALLOWED_HOSTS must be set in production (or RENDER_EXTERNAL_HOSTNAME must exist)."
    )

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set in production (Render Postgres).")


import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', 'sqlite:///db.sqlite3'),
        conn_max_age=600
    )
}
# DATABASE_ROUTERS removed for single db per service setup


#  hardening for HTTPS deployments.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", default=True)

SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)

# X-Forwarded-Proto support (common behind proxies/load balancers)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# In production, be explicit about CORS rather than allowing all origins.
CORS_ALLOW_ALL_ORIGINS = False

# Trust Render-hosted domain(s) for CSRF if you ever use cookie-based auth.
if render_hostname:
    CSRF_TRUSTED_ORIGINS = [f"https://{render_hostname}"]

# WhiteNoise static file storage (Render-friendly) and Cloudinary for Media
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
