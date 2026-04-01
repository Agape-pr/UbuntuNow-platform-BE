import resend
from django.conf import settings


def send_otp_email(email: str, otp: str, purpose: str):
    resend.api_key = settings.RESEND_API_KEY

    params = {
        "from": f"{settings.RESEND_FROM_NAME} <{settings.RESEND_FROM_EMAIL}>",
        "to": [email],
        "template": {
            "id": settings.RESEND_TEMPLATE_OTP_ID,
            "variables": {
                "otp": otp,
                "purpose": purpose.replace("_", " ").title(),
                "expiry_minutes": 5,
            }
        }
    }

    try:
        resend.Emails.send(params)
    except Exception as e:
        raise RuntimeError(f"Resend error: {str(e)}")
