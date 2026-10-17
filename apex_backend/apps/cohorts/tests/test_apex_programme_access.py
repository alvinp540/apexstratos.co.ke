from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

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
    SupportApplication,
    SupportEligibility,
    SupportProgram,
)
from apps.notifications.models import Notification
from apps.profiles.models import Profile

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

    def make_published_assessment(self, field='Software Development', month=1, week=1):
        friday = timezone.make_aware(
            datetime(2026, 10, 16, 9, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        assessment = AssessmentSchedule.objects.create(
            month=month,
            week=week,
            day=4,
            assessment_slot=1,
            field=field,
            title='API scenario',
            description='Apply API design principles to a practical case.',
            learning_objectives=['Interpret', 'Reason', 'Apply'],
            duration_minutes=20,
            status='published',
            scheduled_for=friday,
        )
        for order in range(1, 11):
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

    def create_graded_attempt(self, user, assessment, score, started_at, submitted_at):
        snapshot = {
            'questions': [
                {
                    'id': str(question.id),
                    'prompt': question.prompt,
                    'options': question.options,
                    'correct_answer': question.correct_answer,
                }
                for question in assessment.questions.order_by('order')
            ],
            'scoring_rule': 'Each of ten questions is worth 10 percentage points.',
        }
        attempt = AssessmentScheduleAttempt.objects.create(
            user=user,
            assessment=assessment,
            assessment_snapshot=snapshot,
            status='graded',
            score=score,
            submitted_at=submitted_at,
        )
        AssessmentScheduleAttempt.objects.filter(pk=attempt.pk).update(started_at=started_at)
        attempt.refresh_from_db()
        return attempt

    def test_library_lists_valid_assessments_for_all_eight_weeks_without_answer_keys(self):
        self.make_published_assessment(month=2, week=1)

        response = self.client.get(reverse('contest-assessment-library'), {'week': 5})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        assessment = response.data['results'][0]
        self.assertEqual(assessment['week'], 5)
        self.assertEqual(assessment['question_count'], 10)
        self.assertEqual(assessment['access_price_kes'], 100)
        self.assertFalse(assessment['has_verified_access'])
        self.assertNotIn('video_url', assessment)
        self.assertNotIn('correct_answer', assessment)

    def test_library_topic_filter_searches_title_and_description(self):
        assessment = self.make_published_assessment()

        response = self.client.get(
            reverse('contest-assessment-library'),
            {'topic': 'API design'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(assessment.id))

    def test_library_marks_field_access_only_after_payment_is_verified(self):
        self.make_published_assessment()
        friday = timezone.make_aware(
            datetime(2026, 10, 16, 10, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            locked = self.client.get(reverse('contest-assessment-library'))
        self.assertFalse(locked.data['results'][0]['has_verified_access'])

        self.grant_main_contest_access()
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            unlocked = self.client.get(reverse('contest-assessment-library'))

        self.assertEqual(unlocked.status_code, 200)
        self.assertTrue(unlocked.data['results'][0]['has_verified_access'])
        self.assertTrue(unlocked.data['results'][0]['can_start'])

    def test_library_excludes_assessments_without_ten_valid_questions(self):
        assessment = self.make_published_assessment()
        AssessmentScheduleQuestion.objects.filter(assessment=assessment, order=10).delete()

        response = self.client.get(reverse('contest-assessment-library'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

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

    def test_verified_contest_to_opportunity_application_and_confirmed_payment(self):
        Profile.objects.create(
            user=self.student,
            full_name='Student One',
            profession='software_development',
        )
        program = SupportProgram.objects.create(
            title='Verified Merit Support',
            description='Support after verified contest performance.',
            program_type='philanthropic_support',
            eligibility_rules='At least 70% verified Main Contest average.',
            merit_cutoff=70,
            status='published',
        )
        self.grant_main_contest_access()
        assessment = self.make_published_assessment()
        sunday = timezone.make_aware(
            datetime(2026, 10, 18, 12, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday):
            started = self.client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': assessment.id}),
                {},
                format='json',
            )
            submitted = self.client.post(
                reverse('contest-assessment-submit', kwargs={'attempt_id': started.data['id']}),
                {'answers': {question['id']: 'A' for question in started.data['questions']}},
                format='json',
            )

        self.assertEqual(started.status_code, 201)
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['score'], 100)
        self.assertTrue(SupportEligibility.objects.get(user=self.student, program=program).eligible)
        self.assertTrue(Notification.objects.filter(user=self.student, notification_type='opportunity').exists())

        programs = self.client.get(reverse('support-program-list'))
        self.assertTrue(programs.data['results'][0]['eligible'])
        application = self.client.post(
            reverse('support-application-create', kwargs={'program_id': program.id}),
            {
                'full_name': 'Student One',
                'registered_phone_number': '0712345678',
                'mpesa_number': '0712345678',
            },
            format='json',
        )
        self.assertEqual(application.status_code, 201)
        application_id = application.data['id']

        administrator = User.objects.create_user(
            email='journey-admin@example.test',
            username='journey-admin',
            password='temporary-test-only',
            role='admin',
            is_staff=True,
        )
        self.client.force_authenticate(administrator)
        for next_status in ('under_review', 'approved'):
            decision = self.client.post(
                reverse('support-application-admin-decision', kwargs={'application_id': application_id}),
                {'status': next_status, 'admin_reason': 'Eligibility and details reviewed.'},
                format='json',
            )
            self.assertEqual(decision.status_code, 200)
        program.funding_status = 'funded'
        program.save(update_fields=['funding_status'])
        for next_status in ('payment_processing', 'paid'):
            decision = self.client.post(
                reverse('support-application-admin-decision', kwargs={'application_id': application_id}),
                {
                    'status': next_status,
                    'admin_reason': 'Payment confirmed.' if next_status == 'paid' else 'Processing payment.',
                    'payment_reference': 'JOURNEY-REF',
                },
                format='json',
            )
            self.assertEqual(decision.status_code, 200, decision.data)

        self.client.force_authenticate(self.student)
        tracked = self.client.get(reverse('support-application-list'))
        self.assertEqual(tracked.status_code, 200)
        self.assertEqual(tracked.data[0]['status'], 'paid')
        self.assertIsNotNone(tracked.data[0]['payment_confirmed_at'])
        self.assertEqual(SupportApplication.objects.get(id=application_id).payment_confirmed_by, administrator)

    def test_contest_cycle_leaderboard_reports_eat_rank_and_ties(self):
        assessment = self.make_published_assessment()
        friday = timezone.make_aware(
            datetime(2026, 10, 16, 10, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        self.create_graded_attempt(
            self.student,
            assessment,
            90,
            friday - timedelta(minutes=1),
            friday,
        )
        peer = User.objects.create_user(
            email='cycle-peer@example.test',
            username='cycle-peer',
            password='temporary-test-only',
        )
        self.create_graded_attempt(
            peer,
            assessment,
            90,
            friday - timedelta(minutes=5),
            friday,
        )
        lower_ranked = User.objects.create_user(
            email='cycle-lower@example.test',
            username='cycle-lower',
            password='temporary-test-only',
        )
        self.create_graded_attempt(
            lower_ranked,
            assessment,
            80,
            friday - timedelta(minutes=10),
            friday,
        )

        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            response = self.client.get(reverse('contest-cycle-leaderboard-me'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rank'], 1)
        self.assertEqual(response.data['participant_count'], 3)
        self.assertEqual(response.data['average_score'], 90)
        self.assertEqual(response.data['cycle_start'], friday.replace(hour=0, minute=0))
        self.assertEqual(response.data['tie_break_seconds'], 60)
        self.assertTrue(response.data['tie_break_applied'])
        self.assertEqual(response.data['ranking_status'], 'provisional')

        self.client.force_authenticate(peer)
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            peer_response = self.client.get(reverse('contest-cycle-leaderboard-me'))
        self.assertEqual(peer_response.data['rank'], 2)
        self.assertEqual(peer_response.data['tie_break_seconds'], 300)
        self.client.force_authenticate(lower_ranked)
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            lower_score_response = self.client.get(reverse('contest-cycle-leaderboard-me'))
        self.assertEqual(lower_score_response.data['rank'], 3)

    def test_equal_scores_with_equal_elapsed_time_share_rank(self):
        assessment = self.make_published_assessment()
        friday = timezone.make_aware(
            datetime(2026, 10, 16, 10, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        peer = User.objects.create_user(
            email='same-time-peer@example.test',
            username='same-time-peer',
            password='temporary-test-only',
        )
        for user in (self.student, peer):
            self.create_graded_attempt(
                user,
                assessment,
                90,
                friday - timedelta(minutes=2),
                friday,
            )

        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            response = self.client.get(reverse('contest-cycle-leaderboard-me'))

        self.assertEqual(response.data['rank'], 1)
        self.assertEqual(response.data['tie_break_seconds'], 120)
        self.assertFalse(response.data['tie_break_applied'])
        self.client.force_authenticate(peer)
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            peer_response = self.client.get(reverse('contest-cycle-leaderboard-me'))
        self.assertEqual(peer_response.data['rank'], 1)

    def test_equal_scores_across_different_assessment_sets_share_rank(self):
        assessment = self.make_published_assessment()
        other_assessment = self.make_published_assessment(month=1, week=2)
        friday = timezone.make_aware(
            datetime(2026, 10, 16, 10, 0),
            ZoneInfo('Africa/Nairobi'),
        )
        peer = User.objects.create_user(
            email='different-set-peer@example.test',
            username='different-set-peer',
            password='temporary-test-only',
        )
        self.create_graded_attempt(
            self.student,
            assessment,
            90,
            friday - timedelta(minutes=1),
            friday,
        )
        self.create_graded_attempt(
            peer,
            other_assessment,
            90,
            friday - timedelta(minutes=5),
            friday,
        )

        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            response = self.client.get(reverse('contest-cycle-leaderboard-me'))

        self.assertEqual(response.data['rank'], 1)
        self.assertIsNone(response.data['tie_break_seconds'])
        self.assertFalse(response.data['tie_break_applied'])
        self.client.force_authenticate(peer)
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            peer_response = self.client.get(reverse('contest-cycle-leaderboard-me'))
        self.assertEqual(peer_response.data['rank'], 1)

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

    def test_contest_requires_written_reasoning_when_configured(self):
        self.grant_main_contest_access()
        assessment = self.make_published_assessment()
        question = assessment.questions.get(order=1)
        question.requires_reasoning = True
        question.save(update_fields=['requires_reasoning'])
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
        answers = {item['id']: 'A' for item in started.data['questions']}
        submit_url = reverse('contest-assessment-submit', kwargs={'attempt_id': started.data['id']})
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday + timedelta(minutes=1)):
            missing_reasoning = self.client.post(
                submit_url,
                {'answers': answers},
                format='json',
            )
            submitted = self.client.post(
                submit_url,
                {'answers': answers, 'reasoning': {str(question.id): 'The evidence supports this choice.'}},
                format='json',
            )

        self.assertEqual(missing_reasoning.status_code, 400)
        self.assertEqual(submitted.status_code, 200)
        attempt = AssessmentScheduleAttempt.objects.get()
        self.assertEqual(
            attempt.answers[str(question.id)]['reasoning'],
            'The evidence supports this choice.',
        )
