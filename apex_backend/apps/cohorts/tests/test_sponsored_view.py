from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import (
    ParticipationPayment,
    SponsoredViewAssessment,
    SponsoredViewAttempt,
    SponsoredViewPayment,
    SponsoredViewQuestion,
)
from apps.notifications.models import Notification


EAT = ZoneInfo('Africa/Nairobi')


def eat_datetime(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=EAT)


class SponsoredViewAccessTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email='sponsored-student@example.test',
            username='sponsored-student',
            password='test-password',
        )
        self.admin = User.objects.create_user(
            email='sponsored-admin@example.test',
            username='sponsored-admin',
            password='test-password',
            role='admin',
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.assessment = SponsoredViewAssessment.objects.create(
            week=1,
            slot=1,
            field='Software Development',
            title='Verify an interface contract',
            description='Apply API contract testing to a realistic change.',
            learning_objectives=['Identify the contract', 'Select evidence', 'Explain a test result'],
            duration_minutes=20,
            status='published',
        )
        for order in range(1, 11):
            correct = f'Check the schema in test {order}.'
            SponsoredViewQuestion.objects.create(
                assessment=self.assessment,
                order=order,
                prompt=f'Which action verifies API schema requirement {order}?',
                options=[
                    correct,
                    f'Ignore requirement {order}.',
                    f'Disable validation for {order}.',
                    f'Retry without checking requirement {order}.',
                ],
                correct_answer=correct,
                rationale='A contract test checks observed data against the agreed interface.',
            )

    def create_payment(self, reference='SPONSOREDREF1', now=None):
        with patch(
            'apps.cohorts.sponsored_views.timezone.now',
            return_value=now or eat_datetime(2026, 10, 12, 10),
        ):
            return self.client.post(
                reverse(
                    'sponsored-view-payment-create',
                    kwargs={'assessment_id': self.assessment.id},
                ),
                {'payment_reference': reference},
                format='json',
            )

    def test_catalog_topic_filter_and_verified_access_flag(self):
        matching = self.client.get(
            reverse('sponsored-view-assessment-list'),
            {'topic': 'interface'},
        )
        self.assertEqual(matching.status_code, 200)
        self.assertEqual(matching.data['count'], 1)
        self.assertFalse(matching.data['results'][0]['has_verified_access'])

        unmatched = self.client.get(
            reverse('sponsored-view-assessment-list'),
            {'topic': 'unrelated topic'},
        )
        self.assertEqual(unmatched.status_code, 200)
        self.assertEqual(unmatched.data['count'], 0)

        payment = self.create_payment('SPONSOREDREFACCESS')
        self.assertEqual(payment.status_code, 201)
        self.client.force_authenticate(self.admin)
        verified = self.client.post(
            reverse('sponsored-view-payment-admin-decision', kwargs={'payment_id': payment.data['id']}),
            {
                'status': 'verified',
                'mpesa_transaction_id': 'SPONSOREDTXACCESS',
                'verification_notes': 'Verified for library access test.',
            },
            format='json',
        )
        self.assertEqual(verified.status_code, 200)

        self.client.force_authenticate(self.student)
        unlocked = self.client.get(
            reverse('sponsored-view-assessment-list'),
            {'topic': 'interface'},
        )
        self.assertTrue(unlocked.data['results'][0]['has_verified_access'])

    def test_student_pays_once_admin_verifies_then_student_starts_saves_and_submits(self):
        monday = eat_datetime(2026, 10, 12, 10)
        payment_response = self.create_payment(now=monday)
        self.assertEqual(payment_response.status_code, 201)
        payment_id = payment_response.data['id']
        self.assertEqual(payment_response.data['amount_kes'], 20)

        before_verification = self.client.post(
            reverse('sponsored-view-attempt-start', kwargs={'payment_id': payment_id}),
            {},
            format='json',
        )
        self.assertEqual(before_verification.status_code, 403)

        self.client.force_authenticate(self.admin)
        admin_payments = self.client.get(reverse('sponsored-view-payment-admin-list'))
        self.assertEqual(admin_payments.status_code, 200)
        self.assertEqual(admin_payments.data[0]['amount_kes'], 20)
        verified = self.client.post(
            reverse('sponsored-view-payment-admin-decision', kwargs={'payment_id': payment_id}),
            {
                'status': 'verified',
                'mpesa_transaction_id': 'SPONSOREDTXN1',
                'verification_notes': 'Confirmed against the M-Pesa receipt.',
            },
            format='json',
        )
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data['status'], 'verified')
        self.assertTrue(Notification.objects.filter(user=self.student, notification_type='payment').exists())

        self.client.force_authenticate(self.student)
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday + timedelta(minutes=1)):
            started = self.client.post(
                reverse('sponsored-view-attempt-start', kwargs={'payment_id': payment_id}),
                {},
                format='json',
            )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.data['deadline_at'], monday + timedelta(minutes=21))
        self.assertNotIn('correct_answer', started.data['questions'][0])
        question_id = started.data['questions'][0]['id']
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday + timedelta(minutes=2)):
            saved = self.client.post(
                reverse('sponsored-view-attempt-answers', kwargs={'attempt_id': started.data['id']}),
                {'answers': {question_id: started.data['questions'][0]['options'][1]}, 'reasoning': {}},
                format='json',
            )
            resumed = self.client.post(
                reverse('sponsored-view-attempt-start', kwargs={'payment_id': payment_id}),
                {},
                format='json',
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.data['id'], started.data['id'])
        self.assertEqual(resumed.data['answers'][question_id], started.data['questions'][0]['options'][1])

        correct_answers = {
            question['id']: question['options'][0]
            for question in started.data['questions']
        }
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday + timedelta(minutes=3)):
            submitted = self.client.post(
                reverse('sponsored-view-attempt-submit', kwargs={'attempt_id': started.data['id']}),
                {'answers': correct_answers, 'reasoning': {}},
                format='json',
            )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'graded')
        self.assertEqual(submitted.data['score'], 100)
        self.assertIn('correct_answer', submitted.data['questions'][0])
        self.assertEqual(SponsoredViewAttempt.objects.count(), 1)

    def test_only_weekday_window_allows_payment_requests_and_starts(self):
        friday = eat_datetime(2026, 10, 16)
        closed = self.create_payment('SPONSOREDREF2', now=friday)
        self.assertEqual(closed.status_code, 403)
        self.assertEqual(SponsoredViewPayment.objects.count(), 0)
        invalid_list_post = self.client.post(
            reverse('sponsored-view-payment-list'),
            {},
            format='json',
        )
        self.assertEqual(invalid_list_post.status_code, 405)

    def test_daily_limit_and_duplicate_payment_or_transaction_references_are_enforced(self):
        monday = eat_datetime(2026, 10, 12, 10)
        responses = [
            self.create_payment(f'SPONSOREDREF{index}', now=monday)
            for index in range(1, 6)
        ]
        sixth = self.create_payment('SPONSOREDREF6', now=monday)
        self.assertTrue(all(response.status_code == 201 for response in responses))
        self.assertEqual(sixth.status_code, 429)

        payment = SponsoredViewPayment.objects.first()
        self.client.force_authenticate(self.admin)
        ParticipationPayment.objects.create(
            user=self.student,
            field='Software Development',
            amount_kes=100,
            payment_reference='OTHERPROGRAMREF',
            mpesa_transaction_id='ALREADYUSED',
            status='verified',
        )
        duplicate_txn = self.client.post(
            reverse('sponsored-view-payment-admin-decision', kwargs={'payment_id': payment.id}),
            {
                'status': 'verified',
                'mpesa_transaction_id': 'ALREADYUSED',
            },
            format='json',
        )
        self.assertEqual(duplicate_txn.status_code, 409)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')

    def test_thursday_start_deadline_is_capped_at_friday_eat(self):
        payment_response = self.create_payment('SPONSOREDREF7', now=eat_datetime(2026, 10, 15, 23, 40))
        payment = SponsoredViewPayment.objects.get(id=payment_response.data['id'])
        payment.status = 'verified'
        payment.verified_at = eat_datetime(2026, 10, 15, 23, 41)
        payment.save(update_fields=('status', 'verified_at'))
        with patch(
            'apps.cohorts.sponsored_views.timezone.now',
            return_value=eat_datetime(2026, 10, 15, 23, 50),
        ):
            started = self.client.post(
                reverse('sponsored-view-attempt-start', kwargs={'payment_id': payment.id}),
                {},
                format='json',
            )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.data['deadline_at'], eat_datetime(2026, 10, 16))
