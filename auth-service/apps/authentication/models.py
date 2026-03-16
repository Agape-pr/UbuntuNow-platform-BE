from django.db import models
from django.db.models import Q


class EmailOTP(models.Model):
    PURPOSE_CHOICES = (
        ("register", "Register"),
        ("login", "Login"),
        ("reset_password", "Reset Password"),
    )

    email = models.EmailField()
    code_hash = models.CharField(max_length=64)
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES)

    attempts = models.PositiveSmallIntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    resend_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["email", "purpose"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["email", "purpose"],
                condition=Q(is_verified=False),
                name="unique_active_otp_per_email_purpose"
            )
        ]
        ordering = ["-created_at"]
