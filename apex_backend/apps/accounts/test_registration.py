from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_HOST_USER='mailer@example.com',
    FRONTEND_URL='https://apexstratos.courses',
    REQUIRE_EMAIL_VERIFICATION=True,
)
class RegistrationEmailTests(APITestCase):
    def registration_payload(self):
        return {
            'email': 'new.user@example.com',
            'username': 'new-user',
            'password': 'Test-passphrase-9!Kq',
            'password2': 'Test-passphrase-9!Kq',
            'role': 'professional',
        }

    def test_registration_sends_verification_email_without_worker(self):
        response = self.client.post(
            '/api/v1/auth/register/',
            self.registration_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='new.user@example.com')
        self.assertFalse(user.is_email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['new.user@example.com'])
        self.assertIn(user.email_verification_token, mail.outbox[0].body)

    @override_settings(REQUIRE_EMAIL_VERIFICATION=False, EMAIL_HOST_USER='')
    def test_registration_skips_email_and_verifies_account_for_demo(self):
        response = self.client.post(
            '/api/v1/auth/register/',
            self.registration_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('You can now sign in', response.data['message'])
        user = User.objects.get(email='new.user@example.com')
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.email_verification_token)
        self.assertEqual(len(mail.outbox), 0)

    @patch(
        'apps.accounts.tasks.send_mail',
        side_effect=OSError('SMTP unavailable'),
    )
    def test_registration_returns_error_and_rolls_back_when_email_fails(
        self,
        _send_mail_mock,
    ):
        response = self.client.post(
            '/api/v1/auth/register/',
            self.registration_payload(),
            format='json',
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertFalse(User.objects.filter(
            email='new.user@example.com'
        ).exists())
