from datetime import timedelta

from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.authentication.models import EmailOTP
from apps.authentication.utils.otp import generate_otp, hash_otp

from core.services.email_service import send_otp_email


OTP_EXPIRY_MINUTES = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_RESENDS = 3
MAX_ATTEMPTS = 5



@transaction.atomic
def create_email_otp(email: str, purpose: str) -> str:
    EmailOTP.objects.filter(
        email=email,
        purpose=purpose,
        is_verified=False
    ).delete()

    raw_otp = generate_otp()

    EmailOTP.objects.create(
        email=email,
        purpose=purpose,
        code_hash=hash_otp(raw_otp),
        expires_at=timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    )

    # 🔥 send email here
    send_otp_email(
        email=email,
        otp=raw_otp,
        purpose=purpose
    )

    return raw_otp



@transaction.atomic
def resend_email_otp(email: str, purpose: str) -> str:
    try:
        otp = EmailOTP.objects.select_for_update().get(
            email=email,
            purpose=purpose,
            is_verified=False
        )
    except EmailOTP.DoesNotExist:
        raise ValidationError("OTP not found or already verified")

    cooldown_time = otp.created_at + timedelta(seconds=RESEND_COOLDOWN_SECONDS)
    if timezone.now() < cooldown_time:
        remaining = int((cooldown_time - timezone.now()).total_seconds())
        raise ValidationError(
            f"Please wait {remaining}s before requesting another OTP"
        )

    if otp.resend_count >= MAX_RESENDS:
        otp.delete()
        raise ValidationError("Too many OTP requests. Please restart process.")

    raw_otp = generate_otp()

    otp.code_hash = hash_otp(raw_otp)
    otp.resend_count += 1
    otp.attempts = 0
    otp.created_at = timezone.now()
    otp.expires_at = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    otp.save()

    # 🔥 SEND EMAIL
    send_otp_email(
        email=email,
        otp=raw_otp,
        purpose=purpose
    )

    return raw_otp


@transaction.atomic
def verify_email_otp(email: str, purpose: str, raw_otp: str) -> None:
    try:
        otp = EmailOTP.objects.select_for_update().get(
            email=email,
            purpose=purpose,
            is_verified=False
        )
    except EmailOTP.DoesNotExist:
        raise ValidationError("Invalid or already verified OTP")

    if timezone.now() > otp.expires_at:
        otp.delete()
        raise ValidationError("OTP has expired")

    if otp.attempts >= MAX_ATTEMPTS:
        otp.delete()
        raise ValidationError("Too many failed attempts. OTP invalidated.")

    if otp.code_hash != hash_otp(raw_otp):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        raise ValidationError("Invalid OTP")

    otp.is_verified = True
    otp.save(update_fields=["is_verified"])

