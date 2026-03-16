from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# Dev convenience: allow local frontends by setting env vars.
# Keep default behavior unchanged unless explicitly enabled.
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", default=False)
