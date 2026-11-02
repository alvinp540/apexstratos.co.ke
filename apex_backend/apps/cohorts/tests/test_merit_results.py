from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import AssessmentSchedule, AssessmentScheduleAttempt


class MeritTestResultsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='merit-student@example.test',
            username='merit-student',
            password='test-password',
        )
        self.other_user = User.objects.create_user(
            email='merit-other@example.test',
            username='merit-other',
            password='test-password',
        )
        self.flagged_user = User.objects.create_user(
            email='merit-flagged@example.test',
            username='merit-flagged',
            password='test-password',
        )
        self.assessment = AssessmentSchedule.objects.create(
            month=1,
            week=1,
            day=4,
            assessment_slot=1,
            field='Software Development',
            title='API Contract Assessment',
            description='Assess API contract testing.',
            scheduled_for=timezone.now() + timedelta(days=1),
            status='published',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_returns_personal_final_scores_and_rank_per_test(self):
        now = timezone.now()
        own_attempt = AssessmentScheduleAttempt.objects.create(
            user=self.user,
            assessment=self.assessment,
            status='graded',
            score=80,
            submitted_at=now,
        )
        AssessmentScheduleAttempt.objects.create(
            user=self.other_user,
            assessment=self.assessment,
            status='graded',
            score=90,
            submitted_at=now,
        )
        AssessmentScheduleAttempt.objects.create(
            user=self.flagged_user,
            assessment=self.assessment,
            status='graded',
            score=100,
            submitted_at=now,
            is_flagged=True,
        )

        response = self.client.get(reverse('my-test-results'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0], {
            'id': str(own_attempt.id),
            'test_name': 'API Contract Assessment',
            'test_type': 'Main Contest',
            'category': 'Software Development',
            'score': 80,
            'status': 'graded',
            'rank': 2,
            'participant_count': 2,
            'attempted_at': own_attempt.started_at,
            'completed_at': own_attempt.submitted_at,
        })

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse('my-test-results'))

        self.assertEqual(response.status_code, 401)
