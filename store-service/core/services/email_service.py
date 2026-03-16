from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.conf import settings


def send_otp_email(email: str, otp: str, purpose: str):
    message = Mail(
        from_email=(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
        to_emails=email,
    )

    message.template_id = settings.SENDGRID_TEMPLATE_OTP_ID


    message.dynamic_template_data = {
        "otp": otp,
        "purpose": purpose.replace("_", " ").title(),
        "expiry_minutes": 5,
    }

    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        sg.send(message)
    except Exception as e:
        raise RuntimeError(f"SendGrid error: {str(e)}")
