"""Helpers to write the audit trail (who did what, when)."""
import logging

from .models import AuditLog

logger = logging.getLogger(__name__)


def client_ip(request):
    if request is None:
        return ''
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR') or ''
    return forwarded[:100]


def record(request, action, target_type='', target_id='', metadata=None, actor=None):
    """
    Append an audit entry. Never raises: auditing must not break the action itself.
    ``actor`` defaults to request.user when authenticated.
    """
    try:
        if actor is None and request is not None and getattr(request.user, 'is_authenticated', False):
            actor = request.user
        AuditLog.objects.create(
            actor_id=getattr(actor, 'id', None),
            actor_email=getattr(actor, 'email', '') or '',
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id not in (None, '') else '',
            metadata=metadata or {},
            ip_address=client_ip(request),
        )
    except Exception:
        logger.exception("Failed to write audit log entry %s", action)
