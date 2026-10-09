"""
Service-to-service authentication for internal endpoints.

Internal endpoints (``.../internal/...``) are called by other microservices, never by
end users. They are protected by a shared secret sent in the ``X-Internal-Token``
header and read from the ``INTERNAL_SERVICE_TOKEN`` environment variable, which must
be set to the same value on every service.
"""
import hmac
import logging
import os

from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

INTERNAL_TOKEN_HEADER = "X-Internal-Token"
_INTERNAL_TOKEN_META_KEY = "HTTP_X_INTERNAL_TOKEN"


def _configured_token():
    return os.environ.get("INTERNAL_SERVICE_TOKEN", "").strip()


def internal_headers(extra=None):
    """Headers to attach to a request to another service's internal endpoint."""
    headers = dict(extra or {})
    token = _configured_token()
    if token:
        headers[INTERNAL_TOKEN_HEADER] = token
    else:
        logger.error("INTERNAL_SERVICE_TOKEN is not set; internal service calls will be rejected.")
    return headers


class IsInternalService(BasePermission):
    """Allows access only to requests carrying the shared internal service token."""

    def has_permission(self, request, view):
        expected = _configured_token()
        if not expected:
            # Fail closed: an unconfigured secret must never mean "open".
            logger.error("INTERNAL_SERVICE_TOKEN is not set; rejecting internal request.")
            return False
        provided = request.META.get(_INTERNAL_TOKEN_META_KEY, "")
        return hmac.compare_digest(provided.encode(), expected.encode())
