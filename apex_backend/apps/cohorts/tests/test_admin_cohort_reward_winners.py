from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.cohorts.models import Assessment, AssessmentAttempt, Cohort, CohortEnrollment
from apps.profiles.models import Profile


class AdminCohortRewardWinnersTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='reward-admin@example.test',
            username='reward-admin',
            password='test-password',
            role='admin',
        )
        self.client.force_authenticate(self.admin)

    def make_cohort(self, title):
        return Cohort.objects.create(
            title=title,
            profession='Software Development',
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
        )

    def make_user(self, email, phone_number=''):
        return User.objects.create_user(
            email=email,
            username=email.split('@')[0],
            password='test-password',
            phone_number=phone_number,
        )

    def add_attempt(self, user, cohort, assessment, score, status='graded', is_flagged=False):
        return AssessmentAttempt.objects.create(
            user=user,
            cohort=cohort,
            assessment=assessment,
            score=score,
            status=status,
            is_flagged=is_flagged,
        )

    def test_selects_top_eligible_score_and_returns_minimal_contact_details(self):
        cohort = self.make_cohort('Cohort Alpha')
        winner = self.make_user('winner@example.test', '+254700000001')
        runner_up = self.make_user('runner@example.test', '+254700000002')
        flagged = self.make_user('flagged@example.test')
        unfinished = self.make_user('unfinished@example.test')
        not_enrolled = self.make_user('not-enrolled@example.test')
        for user in (winner, runner_up, flagged, unfinished):
            CohortEnrollment.objects.create(user=user, cohort=cohort)
        Profile.objects.create(
            user=winner,
            full_name='Apex Winner',
            profession='Software Development',
        )

        first_assessment = Assessment.objects.create(cohort=cohort, title='Foundations', instructions='')
        final_assessment = Assessment.objects.create(cohort=cohort, title='Final assessment', instructions='')
        self.add_attempt(winner, cohort, first_assessment, 88)
        self.add_attempt(winner, cohort, final_assessment, 92)
        self.add_attempt(runner_up, cohort, first_assessment, 91)
        self.add_attempt(flagged, cohort, final_assessment, 100, is_flagged=True)
        self.add_attempt(unfinished, cohort, final_assessment, 100, status='submitted')
        self.add_attempt(not_enrolled, cohort, final_assessment, 99)

        response = self.client.get(reverse('admin-cohort-reward-winners'))

        self.assertEqual(response.status_code, 200)
        result = response.data['results'][0]
        self.assertEqual(result['result_status'], 'winner')
        self.assertEqual(result['winners'], [{
            'full_name': 'Apex Winner',
            'email': 'winner@example.test',
            'phone_number': '+254700000001',
            'score': 92.0,
            'assessment': 'Final assessment',
        }])

    def test_tied_top_scores_are_returned_without_a_single_winner(self):
        cohort = self.make_cohort('Tied Cohort')
        assessment = Assessment.objects.create(cohort=cohort, title='Shared assessment', instructions='')
        participants = [
            self.make_user('tie-one@example.test'),
            self.make_user('tie-two@example.test'),
        ]
        for participant in participants:
            CohortEnrollment.objects.create(user=participant, cohort=cohort)
            self.add_attempt(participant, cohort, assessment, 85)

        response = self.client.get(reverse('admin-cohort-reward-winners'))

        result = next(row for row in response.data['results'] if row['cohort_id'] == str(cohort.id))
        self.assertEqual(result['result_status'], 'tied')
        self.assertEqual(len(result['winners']), 2)
        self.assertEqual({winner['score'] for winner in result['winners']}, {85.0})

    def test_cohorts_without_eligible_scores_have_no_winner(self):
        cohort = self.make_cohort('No Scores Cohort')

        response = self.client.get(reverse('admin-cohort-reward-winners'))

        result = next(row for row in response.data['results'] if row['cohort_id'] == str(cohort.id))
        self.assertEqual(result['result_status'], 'no_scores')
        self.assertEqual(result['winners'], [])

    def test_endpoint_is_admin_only(self):
        learner = self.make_user('learner@example.test')
        self.client.force_authenticate(learner)

        self.assertEqual(self.client.get(reverse('admin-cohort-reward-winners')).status_code, 403)

        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(reverse('admin-cohort-reward-winners')).status_code, 401)
