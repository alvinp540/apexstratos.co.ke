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
    Tutorial,
    TutorialProgress,
)
from apps.notifications.models import Notification
from apps.profiles.models import Profile
from apps.cohorts.support_views import get_support_merit


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
        self.assertIn('own verified eligibility workflow', reward['eligibility_reason'])

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
            ('payment_processing', 'Payment instructions issued.', 'MPESA12345'),
            ('paid', 'Payment confirmed.', 'MPESA12345'),
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
