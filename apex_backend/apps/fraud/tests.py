from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import Subscription, User
from apps.fraud.models import AuditLog


class AdminAccountManagementTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='existing-admin@example.test',
            username='existing-admin',
            password='safe-test-password-71',
            role='admin',
            is_staff=True,
        )
        self.client.force_authenticate(self.admin)

    def test_admin_can_create_verified_admin_account_and_audit_it(self):
        response = self.client.post(
            reverse('admin-account-create'),
            {
                'email': 'new-admin@example.test',
                'username': 'new-admin',
                'password': 'Unique-Admin-Pass-482!',
                'password_confirm': 'Unique-Admin-Pass-482!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email='new-admin@example.test')
        self.assertEqual(account.role, 'admin')
        self.assertTrue(account.is_staff)
        self.assertTrue(account.is_email_verified)
        self.assertTrue(account.check_password('Unique-Admin-Pass-482!'))
        self.assertTrue(Subscription.objects.filter(user=account, plan='free').exists())
        self.assertTrue(AuditLog.objects.filter(action='admin_account_created', object_id=str(account.id)).exists())

    def test_non_admin_cannot_create_admin_account(self):
        self.client.force_authenticate(User.objects.create_user(
            email='regular-user@example.test',
            username='regular-user',
            password='safe-test-password-72',
        ))

        response = self.client.post(
            reverse('admin-account-create'),
            {
                'email': 'blocked-admin@example.test',
                'username': 'blocked-admin',
                'password': 'Unique-Admin-Pass-482!',
                'password_confirm': 'Unique-Admin-Pass-482!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='blocked-admin@example.test').exists())

    def test_public_registration_cannot_select_admin_role(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            '/api/v1/auth/register/',
            {
                'email': 'public-admin@example.test',
                'username': 'public-admin',
                'password': 'Unique-Admin-Pass-482!',
                'password2': 'Unique-Admin-Pass-482!',
                'role': 'admin',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email='public-admin@example.test').exists())

    def test_admin_can_promote_existing_user(self):
        target = User.objects.create_user(
            email='promote@example.test',
            username='promote-user',
            password='safe-test-password-73',
        )

        response = self.client.patch(
            reverse('admin-user-role', kwargs={'user_id': target.id}),
            {'role': 'admin'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.role, 'admin')
        self.assertTrue(target.is_staff)
        self.assertTrue(AuditLog.objects.filter(action='user_role_changed', object_id=str(target.id)).exists())

    def test_admin_cannot_demote_self_and_can_demote_another_admin(self):
        self_response = self.client.patch(
            reverse('admin-user-role', kwargs={'user_id': self.admin.id}),
            {'role': 'professional'},
            format='json',
        )
        target = User.objects.create_user(
            email='last-admin@example.test',
            username='last-admin',
            password='safe-test-password-74',
            role='admin',
            is_staff=True,
        )
        last_response = self.client.patch(
            reverse('admin-user-role', kwargs={'user_id': target.id}),
            {'role': 'professional'},
            format='json',
        )

        self.assertEqual(self_response.status_code, 400)
        self.assertEqual(last_response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')
        target.refresh_from_db()
        self.assertEqual(target.role, 'professional')
