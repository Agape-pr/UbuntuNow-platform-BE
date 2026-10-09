from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import EmailOTP

User = get_user_model()
SEND = '/api/v1/auth/otp/email/send/'
RESEND = '/api/v1/auth/otp/resend/'
MAILER = 'apps.authentication.services.otp_service.send_otp_email'


class OtpEnumerationTests(TestCase):
    """The public OTP endpoints must not reveal which emails have accounts."""

    def setUp(self):
        self.client = APIClient()
        User.objects.create_user(username='active@x.com', email='active@x.com', password='Pw-12345678!', is_active=True)
        User.objects.create_user(username='pending@x.com', email='pending@x.com', password='Pw-12345678!', is_active=False)

    def send(self, email, purpose):
        with mock.patch(MAILER) as mailer:
            resp = self.client.post(SEND, {'email': email, 'purpose': purpose}, format='json')
        return resp, mailer

    def test_same_response_for_every_kind_of_email(self):
        cases = [('active@x.com', 'login'), ('nobody@x.com', 'login'), ('pending@x.com', 'login'),
                 ('active@x.com', 'reset_password'), ('nobody@x.com', 'reset_password'),
                 ('pending@x.com', 'register'), ('active@x.com', 'register'), ('nobody@x.com', 'register')]
        for email, purpose in cases:
            resp, _ = self.send(email, purpose)
            self.assertEqual(resp.status_code, 200, (email, purpose))
            self.assertEqual(resp.json(), {'email': email, 'purpose': purpose}, (email, purpose))

    def test_codes_are_only_emailed_when_they_make_sense(self):
        sends = {
            ('active@x.com', 'login'): True, ('active@x.com', 'reset_password'): True,
            ('pending@x.com', 'register'): True,
            ('nobody@x.com', 'login'): False, ('nobody@x.com', 'register'): False,
            ('pending@x.com', 'login'): False,       # not activated yet
            ('active@x.com', 'register'): False,     # already verified
        }
        for (email, purpose), expected in sends.items():
            _, mailer = self.send(email, purpose)
            self.assertEqual(mailer.called, expected, (email, purpose))

    def test_cannot_flood_an_inbox(self):
        _, first = self.send('active@x.com', 'login')
        _, second = self.send('active@x.com', 'login')
        self.assertTrue(first.called)
        self.assertFalse(second.called)
        # ...but once the cooldown has passed a new code goes out.
        EmailOTP.objects.update(created_at=timezone.now() - timedelta(seconds=120))
        _, third = self.send('active@x.com', 'login')
        self.assertTrue(third.called)

    def test_mail_provider_failure_does_not_reveal_the_account(self):
        with mock.patch(MAILER, side_effect=RuntimeError('provider down')):
            real = self.client.post(SEND, {'email': 'active@x.com', 'purpose': 'login'}, format='json')
            fake = self.client.post(SEND, {'email': 'nobody@x.com', 'purpose': 'login'}, format='json')
        self.assertEqual((real.status_code, fake.status_code), (200, 200))

    def test_resend_does_not_reveal_whether_a_code_is_pending(self):
        with mock.patch(MAILER):
            nothing = self.client.post(RESEND, {'email': 'nobody@x.com', 'purpose': 'register'}, format='json')
        self.assertEqual(nothing.status_code, 200)
        self.assertEqual(nothing.json(), {'email': 'nobody@x.com', 'purpose': 'register'})

    def test_registration_still_sends_its_code_and_resend_works(self):
        with mock.patch(MAILER) as mailer:
            created = self.client.post('/api/v1/users/register', {
                'email': 'new@x.com', 'password': 'Str0ng-Passw0rd!x', 'account_type': 'buyer'}, format='json')
            self.assertEqual(created.status_code, 201, created.content)
            self.assertEqual(mailer.call_count, 1)
            EmailOTP.objects.update(created_at=timezone.now() - timedelta(seconds=120))
            resent = self.client.post(RESEND, {'email': 'new@x.com', 'purpose': 'register'}, format='json')
        self.assertEqual(resent.status_code, 200)
        self.assertEqual(mailer.call_count, 2)
