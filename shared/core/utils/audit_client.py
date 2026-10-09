"""Record audit entries in auth-service from other services (best effort, never raises)."""
import logging
import os

import requests

from .internal import internal_headers

logger = logging.getLogger(__name__)


def record_audit(request, action, target_type='', target_id='', metadata=None):
    try:
        user = request.user
        auth_url = os.environ.get('AUTH_SERVICE_URL', 'http://auth-service:8001')
        requests.post(
            f"{auth_url}/api/v1/users/internal/audit/",
            json={
                'actor_id': getattr(user, 'id', None),
                'actor_email': getattr(user, 'email', '') or '',
                'action': action,
                'target_type': target_type,
                'target_id': str(target_id),
                'metadata': metadata or {},
                'ip_address': (request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR') or '')[:100],
            },
            headers=internal_headers(),
            timeout=3,
        )
    except Exception as exc:
        logger.error("Failed to record audit entry %s: %s", action, exc)
