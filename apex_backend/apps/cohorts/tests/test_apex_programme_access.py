from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.cohorts.models import (
    AssessmentSchedule,
    AssessmentScheduleAttempt,
    AssessmentScheduleQuestion,
    ParticipationPayment,
    ParticipationPaymentEvent,
)
from apps.cohorts.programme_views import _attempt_deadline, contest_window_for


class ContestWindowTests(APITestCase):
    def test_sunday_window_closes_at_monday_midnight_eat(self):
        sunday = timezone.make_aware(
            datetime(2026, 10, 18, 23, 50),
            ZoneInfo('Africa/Nairobi'),
        )

        start, end = contest_window_for(sunday)

        self.assertEqual(start, timezone.make_aware(
            datetime(2026, 10, 16, 0, 0),
            ZoneInfo('Africa/Nairobi'),
        ))
        self.assertEqual(end, timezone.make_aware(
            datetime(2026, 10, 19, 0, 0),
            ZoneInfo('Africa/Nairobi'),
        ))
        self.assertEqual(
            _attempt_deadline(sunday, 20 * 60, end),
            end,
        )

    def test_weekday_has_no_open_contest_window(self):
        monday = timezone.make_aware(
            datetime(2026, 10, 19, 0, 0),
            ZoneInfo('Africa/Nairobi'),
        )

        self.assertIsNone(contest_window_for(monday))


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class MainContestAccessTests(APITestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.student = User.objects.create_user(
            email='student@example.test',
            username='student',
            password='test-password',
            phone_number='0712345678',
        )
        self.client.force_authenticate(self.student)

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def payment_data(self, reference='AB123CD'):
        return {
            'full_name': 'Student One',
            'phone_number': '0712345678',
            'field': 'Software Development',
            'program': 'main_contest',
            'amount_kes': 100,
            'payment_reference': reference,
        }

    def make_published_assessment(self, field='Software Development'):
        friday = timezone.make_aware(
            datetime(2026, 10, 16, 9, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        assessment = AssessmentSchedule.objects.create(
            month=1,
            week=1,
            day=4,
            assessment_slot=1,
            field=field,
            title='API scenario',
            description='Apply API design principles to a practical case.',
            learning_objectives=['Interpret', 'Reason', 'Apply'],
            video=SimpleUploadedFile('scenario.mp4', b'video-bytes', content_type='video/mp4'),
            duration_minutes=20,
            status='published',
            scheduled_for=friday,
        )
        for order in range(1, 6):
            AssessmentScheduleQuestion.objects.create(
                assessment=assessment,
                order=order,
                question_type='multiple_choice',
                prompt=f'Choose the justified response for scenario {order}.',
                options=['A', 'B', 'C'],
                correct_answer='A',
                rationale='The evidence supports option A.',
            )
        return assessment

    def grant_main_contest_access(self):
        return ParticipationPayment.objects.create(
            user=self.student,
            full_name='Student One',
            phone_number='0712345678',
            field='Software Development',
            amount_kes=100,
            till_number='1598106',
            payment_reference='AB123CD',
            mpesa_transaction_id='CONFIRMED1',
            status='verified',
            expires_at=timezone.make_aware(
                datetime(2026, 10, 19, 0, 0),
                ZoneInfo('Africa/Nairobi'),
            ),
        )

    def test_payment_request_is_pending_and_does_not_grant_access(self):
        response = self.client.post(
            reverse('main-contest-payment-list'),
            self.payment_data(),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['till_number'], '1598106')
        self.assertEqual(ParticipationPaymentEvent.objects.get().decision, 'submitted')
        self.assertFalse(ParticipationPayment.objects.filter(status='verified').exists())

    def test_duplicate_payment_reference_is_rejected(self):
        first = self.client.post(
            reverse('main-contest-payment-list'),
            self.payment_data(),
            format='json',
        )
        second = self.client.post(
            reverse('main-contest-payment-list'),
            self.payment_data(reference='AB123CD'),
            format='json',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(ParticipationPayment.objects.count(), 1)

    def test_admin_verification_records_evidence_and_immediately_grants_access(self):
        submitted = self.client.post(
            reverse('main-contest-payment-list'),
            self.payment_data(),
            format='json',
        )
        payment_id = submitted.data['id']
        administrator = User.objects.create_user(
            email='admin@example.test',
            username='admin',
            password='test-password',
            role='admin',
        )
        self.client.force_authenticate(administrator)
        access_expiry = timezone.make_aware(
            datetime(2026, 10, 19, 0, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        response = self.client.post(
            reverse('main-contest-payment-decision', kwargs={'payment_id': payment_id}),
            {
                'decision': 'verified',
                'verification_notes': 'Matched to the authorized M-Pesa transaction evidence.',
                'confirmed_transaction_id': 'CONFIRM123',
                'expires_at': access_expiry.isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'verified')
        payment = ParticipationPayment.objects.get(id=payment_id)
        self.assertEqual(payment.verified_by, administrator)
        self.assertEqual(payment.expires_at, access_expiry)
        self.assertEqual(
            list(payment.events.values_list('decision', flat=True)),
            ['submitted', 'verified'],
        )

        repeated = self.client.post(
            reverse('main-contest-payment-decision', kwargs={'payment_id': payment_id}),
            {
                'decision': 'verified',
                'verification_notes': 'Repeated decision',
                'confirmed_transaction_id': 'CONFIRM123',
                'expires_at': access_expiry.isoformat(),
            },
            format='json',
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(payment.events.count(), 2)

    def test_admin_cannot_verify_without_an_access_period_expiry(self):
        submitted = self.client.post(
            reverse('main-contest-payment-list'),
            self.payment_data(),
            format='json',
        )
        administrator = User.objects.create_user(
            email='admin@example.test',
            username='admin',
            password='test-password',
            role='admin',
        )
        self.client.force_authenticate(administrator)
        response = self.client.post(
            reverse('main-contest-payment-decision', kwargs={'payment_id': submitted.data['id']}),
            {
                'decision': 'verified',
                'verification_notes': 'Matched to payment evidence.',
                'confirmed_transaction_id': 'CONFIRM123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ParticipationPayment.objects.get().status, 'pending')

    def test_student_cannot_start_without_verified_study_area_payment(self):
        assessment = self.make_published_assessment()
        sunday = timezone.make_aware(
            datetime(2026, 10, 18, 12, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday):
            response = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(AssessmentScheduleAttempt.objects.count(), 0)

    def test_assessment_cannot_be_started_at_monday_midnight_eat(self):
        self.grant_main_contest_access()
        assessment = self.make_published_assessment()
        monday = timezone.make_aware(
            datetime(2026, 10, 19, 0, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=monday):
            response = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(AssessmentScheduleAttempt.objects.count(), 0)

    def test_verified_payment_starts_once_and_deadline_is_capped_at_monday(self):
        self.grant_main_contest_access()
        assessment = self.make_published_assessment()
        sunday = timezone.make_aware(
            datetime(2026, 10, 18, 23, 50),
            ZoneInfo('Africa/Nairobi'),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday):
            first = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )
            second = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(
            first.data['deadline_at'],
            timezone.make_aware(datetime(2026, 10, 19, 0, 0), ZoneInfo('Africa/Nairobi')),
        )
        self.assertNotIn('correct_answer', first.data['questions'][0])
        self.assertEqual(AssessmentScheduleAttempt.objects.count(), 1)

    def test_assessment_attempt_resumes_with_fixed_deadline_after_content_edit(self):
        self.grant_main_contest_access()
        assessment = self.make_published_assessment()
        sunday = timezone.make_aware(
            datetime(2026, 10, 18, 23, 30),
            ZoneInfo('Africa/Nairobi'),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday):
            first = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )

        attempt = AssessmentScheduleAttempt.objects.get()
        original_deadline = attempt.deadline_at
        stored_snapshot = attempt.assessment_snapshot
        assessment.title = 'Changed after attempt start'
        assessment.save(update_fields=['title'])

        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday + timedelta(minutes=1)):
            resumed = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )

        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.data['id'], first.data['id'])
        self.assertEqual(resumed.data['title'], stored_snapshot['title'])
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline_at, original_deadline)

    def test_submission_is_server_scored_and_idempotent(self):
        self.grant_main_contest_access()
        assessment = self.make_published_assessment()
        sunday = timezone.make_aware(
            datetime(2026, 10, 18, 20, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday):
            started = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )
        answers = {question['id']: 'A' for question in started.data['questions']}
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday + timedelta(minutes=1)):
            first = self.client.post(
                reverse('contest-assessment-submit', kwargs={'attempt_id': started.data['id']}),
                {'answers': answers},
                format='json',
            )
            second = self.client.post(
                reverse('contest-assessment-submit', kwargs={'attempt_id': started.data['id']}),
                {'answers': answers},
                format='json',
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['score'], 100)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['score'], first.data['score'])
        self.assertEqual(AssessmentScheduleAttempt.objects.count(), 1)
