import secrets
import hashlib
from django.conf import settings


OTP_LENGTH = 6


def generate_otp() -> str:
    """
    Generate a cryptographically secure 6-digit OTP.
    """
    return f"{secrets.randbelow(900000) + 100000}"


def hash_otp(otp: str) -> str:
    """
    Hash OTP before storing in DB (similar to password hashing).
    """
    secret = settings.SECRET_KEY
    return hashlib.sha256(f"{otp}{secret}".encode()).hexdigest()


def verify_otp(raw_otp: str, hashed_otp: str) -> bool:
    """
    Verify OTP by comparing hash values.
    """
    return hash_otp(raw_otp) == hashed_otp
