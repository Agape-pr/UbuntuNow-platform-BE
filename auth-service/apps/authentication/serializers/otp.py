from rest_framework import serializers


class SendEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(
        choices=["register", "login", "reset_password"]
    )


class VerifyEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(
        choices=["register", "login", "reset_password"]
    )
    otp = serializers.CharField(min_length=6, max_length=6)


class ResendEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(
        choices=["register", "login", "reset_password"]
    )
