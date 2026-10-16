from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import (
    AssessmentSchedule,
    AssessmentScheduleAttempt,
    SupportApplication,
    SupportApplicationEvent,
    SupportEligibility,
    SupportProgram,
    SponsoredViewAssessment,
    SponsoredViewAttempt,
    SponsoredViewPayment,
    Tutorial,
    TutorialProgress,
)
from apps.notifications.models import Notification
from apps.profiles.models import Profile
from apps.cohorts.support_views import get_support_merit, sync_support_eligibilities_for_user


class SupportApplicationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email='support-student@example.test',
            username='support-student',
            password='temporary-test-only',
            phone_number='0712345678',
        )
        Profile.objects.create(
            user=self.student,
            full_name='Student One',
            profession='software_development',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.program = SupportProgram.objects.create(
            title='Learning Equipment Support',
            description='Support for eligible learners.',
            program_type='philanthropic_support',
            eligibility_rules='Meet the published merit cutoff and submit verified details.',
            merit_cutoff=70,
            status='published',
        )

    def make_contest_attempt(self, score, *, flagged=False):
        assessment_slot = AssessmentSchedule.objects.count() + 1
        assessment = AssessmentSchedule.objects.create(
            month=1,
            week=1,
            day=4,
            assessment_slot=assessment_slot,
            field='Software Development',
            title=f'Assessment {score}',
            description='A text-based contest assessment.',
            learning_objectives=['Apply evidence', 'Reason clearly', 'Choose safely'],
            duration_minutes=20,
            status='published',
            scheduled_for=timezone.now() - timedelta(days=1),
        )
        return AssessmentScheduleAttempt.objects.create(
            user=self.student,
            assessment=assessment,
            status='graded',
            score=score,
            is_flagged=flagged,
        )

    def make_application(self):
        self.make_contest_attempt(80)
        response = self.client.post(
            reverse('support-application-create', kwargs={'program_id': self.program.id}),
            {
                'full_name': 'Student One',
                'registered_phone_number': '0712345678',
                'mpesa_number': '+254712345678',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        return response

    def test_merit_averages_unflagged_completed_contests_and_tracks_tutorial_weeks(self):
        self.make_contest_attempt(80)
        self.make_contest_attempt(100)
        self.make_contest_attempt(0, flagged=True)
        for month, week in ((1, 1), (2, 1)):
            tutorial = Tutorial.objects.create(
                month=month,
                week=week,
                day=0,
                daily_slot=1,
                field='Software Development',
                title=f'Tutorial week {week}',
                description='A published text lesson.',
                learning_objectives=['Learn', 'Practice', 'Apply'],
                difficulty='foundation',
                duration_minutes=20,
                scheduled_for=timezone.now(),
                status='published',
            )
            TutorialProgress.objects.create(
                user=self.student,
                tutorial=tutorial,
                completed_at=timezone.now(),
            )

        self.assertEqual(get_support_merit(self.student), (90.0, 2, 2))

    def test_eligible_program_notifies_and_exposes_only_private_application_for_user(self):
        self.make_contest_attempt(80)

        response = self.client.get(reverse('support-program-list'))

        self.assertEqual(response.status_code, 200)
        program = response.data['results'][0]
        self.assertTrue(program['eligible'])
        self.assertEqual(program['merit_score'], 80)
        self.assertNotIn('phone_number', program)
        self.assertEqual(SupportEligibility.objects.get().merit_cutoff_at_eligibility, 70)
        notification = Notification.objects.get(user=self.student)
        self.assertEqual(notification.action_url, '/opportunities')
        self.assertEqual(notification.metadata['program_id'], str(self.program.id))

    def test_contest_submission_automatically_evaluates_eligibility(self):
        assessment = AssessmentSchedule.objects.create(
            month=1,
            week=1,
            day=4,
            assessment_slot=1,
            field='Software Development',
            title='Verified contest',
            description='A scenario-based assessment.',
            learning_objectives=['Apply verified evidence.'],
            duration_minutes=20,
            status='published',
            scheduled_for=timezone.now() - timedelta(days=1),
        )
        questions = [
            {
                'id': f'question-{index}',
                'options': ['A', 'B', 'C', 'D'],
                'correct_answer': 'A',
            }
            for index in range(10)
        ]
        attempt = AssessmentScheduleAttempt.objects.create(
            user=self.student,
            assessment=assessment,
            status='in_progress',
            deadline_at=timezone.now() + timedelta(minutes=20),
            assessment_snapshot={'questions': questions},
        )

        response = self.client.post(
            reverse('contest-assessment-submit', kwargs={'attempt_id': attempt.id}),
            {'answers': {question['id']: 'A' for question in questions}},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['score'], 100)
        eligibility = SupportEligibility.objects.get(user=self.student, program=self.program)
        self.assertTrue(eligibility.eligible)
        self.assertEqual(eligibility.completed_contests, 1)
        self.assertEqual(Notification.objects.filter(user=self.student, notification_type='opportunity').count(), 1)

        repeated = self.client.post(
            reverse('contest-assessment-submit', kwargs={'attempt_id': attempt.id}),
            {'answers': {question['id']: 'A' for question in questions}},
            format='json',
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(Notification.objects.filter(user=self.student, notification_type='opportunity').count(), 1)

    def test_changed_verified_result_revokes_eligibility_and_notifies(self):
        attempt = self.make_contest_attempt(80)
        self.client.get(reverse('support-program-list'))
        eligibility = SupportEligibility.objects.get(user=self.student, program=self.program)
        self.assertTrue(eligibility.eligible)

        attempt.is_flagged = True
        attempt.save(update_fields=['is_flagged'])
        sync_support_eligibilities_for_user(self.student)

        eligibility.refresh_from_db()
        self.assertFalse(eligibility.eligible)
        self.assertEqual(
            Notification.objects.filter(
                user=self.student,
                title='Opportunity eligibility changed',
            ).count(),
            1,
        )

    def test_sponsored_view_reward_does_not_inherit_main_contest_eligibility(self):
        reward_program = SupportProgram.objects.create(
            title='Sponsored View reward cycle',
            description='A separate Sponsored View reward programme.',
            program_type='sponsored_view_reward',
            eligibility_rules='Separate reward-cycle rules are required.',
            merit_cutoff=0,
            status='published',
        )
        self.make_contest_attempt(100)

        response = self.client.get(reverse('support-program-list'))
        reward = next(
            program for program in response.data['results']
            if program['id'] == str(reward_program.id)
        )
        self.assertFalse(reward['eligible'])
        self.assertIn('configure and publish eligibility criteria', reward['eligibility_reason'])

        application = self.client.post(
            reverse('support-application-create', kwargs={'program_id': reward_program.id}),
            {
                'full_name': 'Student One',
                'registered_phone_number': '0712345678',
                'mpesa_number': '0712345678',
            },
            format='json',
        )
        self.assertEqual(application.status_code, 403)
        self.assertFalse(SupportApplication.objects.filter(program=reward_program).exists())

    def test_sponsored_view_reward_uses_its_configured_verified_metric_and_form(self):
        reward_program = SupportProgram.objects.create(
            title='Sponsored View Practice Reward',
            description='A separate, rule-configured Sponsored View programme.',
            program_type='sponsored_view_reward',
            eligibility_rules='At least 80% from one verified Sponsored View attempt.',
            merit_cutoff=0,
            eligibility_config={
                'source': 'sponsored_view_average',
                'minimum_score': 80,
                'minimum_attempts': 1,
            },
            application_fields=[{
                'key': 'support_reason',
                'label': 'How will this support help?',
                'type': 'textarea',
                'required': True,
                'max_length': 500,
            }],
            status='published',
        )
        assessment = SponsoredViewAssessment.objects.create(
            week=1,
            slot=1,
            field='Software Development',
            title='Sponsored assessment',
            description='A verified practice assessment.',
            learning_objectives=['Apply the concept.', 'Assess evidence.', 'Explain a decision.'],
            duration_minutes=20,
            status='published',
        )
        payment = SponsoredViewPayment.objects.create(
            user=self.student,
            assessment=assessment,
            amount_kes=20,
            payment_reference='SUPPORT-VERIFIED-PAYMENT',
            status='verified',
            verified_at=timezone.now(),
        )
        question_snapshot = [
            {
                'id': f'sponsored-question-{index}',
                'order': index + 1,
                'prompt': f'Choose the verified response for case {index + 1}.',
                'options': ['A', 'B', 'C', 'D'],
                'correct_answer': 'A',
                'rationale': 'The selected response matches the verified evidence.',
                'requires_reasoning': False,
            }
            for index in range(10)
        ]
        attempt = SponsoredViewAttempt.objects.create(
            payment=payment,
            user=self.student,
            assessment=assessment,
            question_snapshot=question_snapshot,
            status='in_progress',
            deadline_at=timezone.now() + timedelta(minutes=20),
        )

        submitted = self.client.post(
            reverse('sponsored-view-attempt-submit', kwargs={'attempt_id': attempt.id}),
            {
                'answers': {
                    question['id']: ('A' if index < 9 else 'B')
                    for index, question in enumerate(question_snapshot)
                },
            },
            format='json',
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['score'], 90)
        self.assertTrue(SupportEligibility.objects.get(user=self.student, program=reward_program).eligible)

        programs = self.client.get(reverse('support-program-list'))
        reward = next(
            item for item in programs.data['results']
            if item['id'] == str(reward_program.id)
        )
        self.assertTrue(reward['eligible'])
        self.assertEqual(reward['eligibility_source'], 'sponsored_view_average')
        self.assertEqual(reward['merit_score'], 90)
        self.assertEqual(
            reward['application_fields'][0]['key'],
            'support_reason',
        )

        payload = {
            'full_name': 'Student One',
            'registered_phone_number': '0712345678',
            'mpesa_number': '+254712345678',
            'application_data': {},
        }
        missing_answer = self.client.post(
            reverse('support-application-create', kwargs={'program_id': reward_program.id}),
            payload,
            format='json',
        )
        self.assertEqual(missing_answer.status_code, 400)
        payload['application_data'] = {'support_reason': 'I will use it to buy required learning materials.'}
        application = self.client.post(
            reverse('support-application-create', kwargs={'program_id': reward_program.id}),
            payload,
            format='json',
        )
        self.assertEqual(application.status_code, 201)
        self.assertEqual(
            application.data['application_data']['support_reason'],
            payload['application_data']['support_reason'],
        )
        self.assertEqual(
            application.data['application_fields_at_application'],
            reward_program.application_fields,
        )

    def test_application_requires_current_registered_identity_and_is_private(self):
        self.make_contest_attempt(80)
        wrong_identity = self.client.post(
            reverse('support-application-create', kwargs={'program_id': self.program.id}),
            {
                'full_name': 'Different Name',
                'registered_phone_number': '0712345678',
                'mpesa_number': '0712345678',
            },
            format='json',
        )
        self.assertEqual(wrong_identity.status_code, 400)
        self.assertEqual(SupportApplication.objects.count(), 0)

        response = self.client.post(
            reverse('support-application-create', kwargs={'program_id': self.program.id}),
            {
                'full_name': 'Student One',
                'registered_phone_number': '0712345678',
                'mpesa_number': '0712345678',
            },
            format='json',
        )
        duplicate = self.client.post(
            reverse('support-application-create', kwargs={'program_id': self.program.id}),
            {
                'full_name': 'Student One',
                'registered_phone_number': '0712345678',
                'mpesa_number': '0712345678',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'submitted')
        self.assertEqual(response.data['program_title'], 'Learning Equipment Support')
        self.assertEqual(response.data['mpesa_number'], '0712345678')
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(SupportApplicationEvent.objects.filter(application__user=self.student).count(), 1)

        other_student = User.objects.create_user(
            email='other-student@example.test',
            username='other-student',
            password='temporary-test-only',
        )
        self.client.force_authenticate(other_student)
        private_list = self.client.get(reverse('support-application-list'))
        self.assertEqual(private_list.status_code, 200)
        self.assertEqual(private_list.data, [])

    def test_admin_can_review_and_confirm_payment_with_audit_events(self):
        self.make_application()
        application = SupportApplication.objects.get()
        administrator = User.objects.create_user(
            email='support-admin@example.test',
            username='support-admin',
            password='temporary-test-only',
            role='admin',
            is_staff=True,
        )
        self.client.force_authenticate(administrator)
        admin_list = self.client.get(reverse('support-application-admin-list'))
        self.assertEqual(admin_list.status_code, 200)
        self.assertEqual(admin_list.data[0]['mpesa_number'], '+254712345678')

        response = self.client.post(
            reverse('support-application-admin-decision', kwargs={'application_id': application.id}),
            {
                'status': 'payment_processing',
                'admin_reason': 'Payment instructions issued.',
                'payment_reference': 'MPESA12345',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.program.funding_status = 'funded'
        self.program.save(update_fields=['funding_status'])

        for next_status, reason, payment_reference in (
            ('under_review', 'Checking submitted details.', ''),
            ('approved', 'Details verified.', ''),
            ('awaiting_funding', 'Approved subject to programme funding.', ''),
        ):
            response = self.client.post(
                reverse('support-application-admin-decision', kwargs={'application_id': application.id}),
                {
                    'status': next_status,
                    'admin_reason': reason,
                    'payment_reference': payment_reference,
                },
                format='json',
            )
            self.assertEqual(response.status_code, 200, response.data)

        response = self.client.post(
            reverse('support-application-admin-decision', kwargs={'application_id': application.id}),
            {'status': 'payment_processing', 'admin_reason': 'Payment instructions issued.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('support-application-admin-decision', kwargs={'application_id': application.id}),
            {'status': 'paid', 'admin_reason': 'Payment confirmation attempted without a reference.'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            reverse('support-application-admin-decision', kwargs={'application_id': application.id}),
            {
                'status': 'paid',
                'admin_reason': 'Payment confirmed.',
                'payment_reference': 'MPESA12345',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)

        application.refresh_from_db()
        self.assertEqual(application.status, 'paid')
        self.assertEqual(application.payment_reference, 'MPESA12345')
        self.assertEqual(application.payment_confirmed_by, administrator)
        self.assertIsNotNone(application.payment_confirmed_at)
        self.assertEqual(SupportApplicationEvent.objects.filter(application=application).count(), 6)

    def test_non_admin_cannot_access_submitted_payment_details(self):
        self.make_application()
        response = self.client.get(reverse('support-application-admin-list'))

        self.assertEqual(response.status_code, 403)

    def test_requested_information_can_be_resubmitted_and_admin_decisions_notify(self):
        self.make_application()
        application = SupportApplication.objects.get()
        administrator = User.objects.create_user(
            email='information-admin@example.test',
            username='information-admin',
            password='temporary-test-only',
            role='admin',
            is_staff=True,
        )
        self.client.force_authenticate(administrator)
        response = self.client.post(
            reverse('support-application-admin-decision', kwargs={'application_id': application.id}),
            {'status': 'under_review', 'admin_reason': 'Checking the application.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('support-application-admin-decision', kwargs={'application_id': application.id}),
            {'status': 'awaiting_information', 'admin_reason': 'Please confirm your M-Pesa number.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'awaiting_information')
        self.assertTrue(Notification.objects.filter(
            user=self.student,
            title='Opportunity application updated',
            message__contains='awaiting information',
        ).exists())

        other_student = User.objects.create_user(
            email='another-student@example.test',
            username='another-student',
            password='temporary-test-only',
        )
        self.client.force_authenticate(other_student)
        private_update = self.client.patch(
            reverse('support-application-information', kwargs={'application_id': application.id}),
            {'mpesa_number': '+254722222222'},
            format='json',
        )
        self.assertEqual(private_update.status_code, 404)

        self.client.force_authenticate(self.student)
        response = self.client.patch(
            reverse('support-application-information', kwargs={'application_id': application.id}),
            {'mpesa_number': '+254722222222'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'submitted')
        self.assertEqual(response.data['mpesa_number'], '+254722222222')
        self.assertEqual(response.data['admin_reason'], '')
        self.assertEqual(SupportApplicationEvent.objects.filter(application=application).count(), 4)

    def test_awaiting_information_can_update_custom_answers_with_validation(self):
        self.program.application_fields = [{
            'key': 'support_reason',
            'label': 'Reason for support',
            'type': 'textarea',
            'required': True,
            'max_length': 300,
        }]
        self.program.save(update_fields=['application_fields'])
        self.make_contest_attempt(80)
        created = self.client.post(
            reverse('support-application-create', kwargs={'program_id': self.program.id}),
            {
                'full_name': 'Student One',
                'registered_phone_number': '0712345678',
                'mpesa_number': '0712345678',
                'application_data': {'support_reason': 'To continue my learning.'},
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        application = SupportApplication.objects.get()
        application.status = 'awaiting_information'
        application.save(update_fields=['status'])

        invalid = self.client.patch(
            reverse('support-application-information', kwargs={'application_id': application.id}),
            {'application_data': {'support_reason': 'x' * 301}},
            format='json',
        )
        self.assertEqual(invalid.status_code, 400)
        application.refresh_from_db()
        self.assertEqual(application.status, 'awaiting_information')

        updated = self.client.patch(
            reverse('support-application-information', kwargs={'application_id': application.id}),
            {
                'application_data': {
                    'support_reason': 'I need the listed equipment for practical work.',
                },
            },
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['status'], 'submitted')
        self.assertEqual(
            updated.data['application_data']['support_reason'],
            'I need the listed equipment for practical work.',
        )
