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

    def create_payment(self, reference='SPONSOREDREF1', now=None, assessment_id=None):
        with patch(
            'apps.cohorts.sponsored_views.timezone.now',
            return_value=now or eat_datetime(2026, 10, 12, 10),
        ):
            return self.client.post(
                reverse(
                    'sponsored-view-payment-create',
                    kwargs={'assessment_id': assessment_id or self.assessment.id},
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
        self.assertEqual(started.data['deadline_at'], monday + timedelta(minutes=6))
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

    def test_timeout_grades_only_saved_answers_and_repeated_finalize_is_idempotent(self):
        monday = eat_datetime(2026, 10, 12, 10)
        payment = self.create_payment('SPONSORED_TIMEOUT', now=monday)
        self.client.force_authenticate(self.admin)
        verified = self.client.post(
            reverse('sponsored-view-payment-admin-decision', kwargs={'payment_id': payment.data['id']}),
            {'status': 'verified', 'mpesa_transaction_id': 'SPONSORED-TIMEOUT-TXN'},
            format='json',
        )
        self.assertEqual(verified.status_code, 200)
        self.client.force_authenticate(self.student)
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday):
            started = self.client.post(
                reverse('sponsored-view-attempt-start', kwargs={'payment_id': payment.data['id']}),
                {}, format='json',
            )
        self.assertEqual(started.data['deadline_at'], monday + timedelta(seconds=300))
        first = started.data['questions'][0]
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday + timedelta(minutes=4, seconds=55)):
            saved = self.client.post(
                reverse('sponsored-view-attempt-answers', kwargs={'attempt_id': started.data['id']}),
                {'answers': {first['id']: first['options'][0]}, 'reasoning': {}}, format='json',
            )
        self.assertEqual(saved.status_code, 200)
        late_answers = {question['id']: question['options'][0] for question in started.data['questions']}
        submit_url = reverse('sponsored-view-attempt-submit', kwargs={'attempt_id': started.data['id']})
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday + timedelta(seconds=300)):
            finalized = self.client.post(submit_url, {'answers': late_answers}, format='json')
            repeated = self.client.post(submit_url, {'answers': late_answers}, format='json')
        self.assertEqual(finalized.data['status'], 'timed_out')
        self.assertEqual(finalized.data['score'], 10)
        self.assertEqual(repeated.data['score'], 10)
        attempt = SponsoredViewAttempt.objects.get()
        self.assertEqual(attempt.status, 'timed_out')
        self.assertEqual(len(attempt.answers), 1)

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

    def test_capability_limit_and_duplicate_payment_or_transaction_references_are_enforced(self):
        monday = eat_datetime(2026, 10, 12, 10)
        assessments = [self.assessment]
        for slot in range(2, 7):
            assessment = SponsoredViewAssessment.objects.create(
                week=1, slot=slot, field='Software Development', title=f'Capability assessment {slot}',
                description='A capability-limit assessment.',
                learning_objectives=['A', 'B', 'C'], status='published',
            )
            for order in range(1, 11):
                SponsoredViewQuestion.objects.create(
                    assessment=assessment, order=order, prompt=f'Question {order}',
                    options=['A', 'B', 'C', 'D'], correct_answer='A', rationale='Test rationale',
                )
            assessments.append(assessment)
        responses = [
            self.create_payment(f'SPONSOREDREF{index}', now=monday, assessment_id=assessment.id)
            for index, assessment in enumerate(assessments[:5], start=1)
        ]
        sixth = self.create_payment('SPONSOREDREF6', now=monday, assessment_id=assessments[5].id)
        self.assertTrue(all(response.status_code == 201 for response in responses), [(response.status_code, response.data) for response in responses])
        self.assertEqual(sixth.status_code, 409)
        self.assertIn('maximum of five active entries', sixth.data['error'])
        other_capability = SponsoredViewAssessment.objects.create(
            week=1, slot=9, field='Finance', title='Independent capability entry',
            description='A second capability remains available.',
            learning_objectives=['A', 'B', 'C'], status='published',
        )
        for order in range(1, 11):
            SponsoredViewQuestion.objects.create(
                assessment=other_capability, order=order, prompt=f'Finance question {order}',
                options=['A', 'B', 'C', 'D'], correct_answer='A', rationale='Test rationale',
            )
        other = self.create_payment(
            'OTHER-CAPABILITY-ENTRY', now=monday, assessment_id=other_capability.id,
        )
        self.assertEqual(other.status_code, 201)

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

    def test_thursday_attempt_keeps_its_full_five_minutes_across_activity_boundary(self):
        payment_response = self.create_payment('SPONSOREDREF7', now=eat_datetime(2026, 10, 15, 23, 40))
        payment = SponsoredViewPayment.objects.get(id=payment_response.data['id'])
        payment.status = 'verified'
        payment.verified_at = eat_datetime(2026, 10, 15, 23, 41)
        payment.save(update_fields=('status', 'verified_at'))
        with patch(
            'apps.cohorts.sponsored_views.timezone.now',
            return_value=eat_datetime(2026, 10, 15, 23, 57),
        ):
            started = self.client.post(
                reverse('sponsored-view-attempt-start', kwargs={'payment_id': payment.id}),
                {},
                format='json',
            )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.data['deadline_at'], eat_datetime(2026, 10, 16, 0, 2))
