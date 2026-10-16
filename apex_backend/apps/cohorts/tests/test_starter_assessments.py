from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import (
    AssessmentSchedule,
    AssessmentScheduleQuestion,
    ParticipationPayment,
    SponsoredViewAssessment,
    SponsoredViewPayment,
    SponsoredViewQuestion,
    Tutorial,
    TutorialQuestion,
)


EAT = ZoneInfo('Africa/Nairobi')
STARTER_PACKS = {
    'tutorials': 'tutorial.json',
    'sponsored-view': 'sponsored-view.json',
    'main-contest': 'main-contest.json',
}


def eat_datetime(day, hour=10):
    return datetime(2026, 10, day, hour, tzinfo=EAT)


class StarterAssessmentJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        pack_root = Path(__file__).resolve().parents[3] / 'content_packs' / 'original' / 'starter'
        for filename in STARTER_PACKS.values():
            if not (pack_root / filename).is_file():
                raise AssertionError(f'Missing starter assessment fixture: {filename}')
        call_command('seed_apexstratos_starter_libraries', '--apply', stdout=StringIO())

        cls.tutorial = Tutorial.objects.get(
            imported_external_id='apex-starter-software-tutorial-w1-v1',
        )
        cls.sponsored = SponsoredViewAssessment.objects.get(
            imported_external_id='apex-starter-software-sponsored-w1-v1',
        )
        cls.contest = AssessmentSchedule.objects.get(
            imported_external_id='apex-starter-software-contest-w1-v1',
        )

    def setUp(self):
        self.student = User.objects.create_user(
            email='starter-student@example.test',
            username='starter-student',
            password='test-password',
            phone_number='0712345678',
        )
        self.admin = User.objects.create_user(
            email='starter-admin@example.test',
            username='starter-admin',
            password='test-password',
            role='admin',
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def submit_all_correct(self, started, question_model, assessment, relation_field='assessment'):
        questions = {
            str(question.id): question.correct_answer
            for question in question_model.objects.filter(**{relation_field: assessment})
        }
        answers = {
            question['id']: questions[question['id']]
            for question in started.data['questions']
        }
        return answers

    def test_published_tutorial_is_listed_started_and_graded(self):
        monday = eat_datetime(12)
        with patch('apps.cohorts.views.timezone.now', return_value=monday):
            library = self.client.get(reverse('tutorial-list'), {'field': 'Software Development'})
            self.assertEqual(library.status_code, 200)
            self.assertEqual(library.data['count'], 1)
            detail = self.client.get(
                reverse('tutorial-detail', kwargs={'tutorial_id': self.tutorial.id}),
            )
            self.assertEqual(detail.status_code, 200)
            started = self.client.post(
                reverse('tutorial-attempt-start', kwargs={'tutorial_id': self.tutorial.id}),
                {},
                format='json',
            )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(len(started.data['questions']), 10)
        self.assertNotIn('correct_answer', started.data['questions'][0])

        answers = self.submit_all_correct(
            started,
            TutorialQuestion,
            self.tutorial,
            relation_field='tutorial',
        )
        with patch('apps.cohorts.views.timezone.now', return_value=monday + timedelta(minutes=1)):
            submitted = self.client.post(
                reverse('tutorial-attempt-submit', kwargs={'attempt_id': started.data['id']}),
                {'answers': answers},
                format='json',
            )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'graded')
        self.assertEqual(submitted.data['score'], 100)

    def test_sponsored_view_requires_verified_payment_then_starts_and_grades(self):
        monday = eat_datetime(12)
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday):
            library = self.client.get(
                reverse('sponsored-view-assessment-list'),
                {'field': 'Software Development'},
            )
            self.assertEqual(library.status_code, 200)
            self.assertEqual(library.data['count'], 1)
            self.assertFalse(library.data['results'][0]['can_start'])
            payment = self.client.post(
                reverse(
                    'sponsored-view-payment-create',
                    kwargs={'assessment_id': self.sponsored.id},
                ),
                {'payment_reference': 'STARTERSPONSOR1'},
                format='json',
            )
        self.assertEqual(payment.status_code, 201)
        self.assertEqual(payment.data['status'], 'pending')

        self.client.force_authenticate(self.admin)
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday):
            verified = self.client.post(
                reverse(
                    'sponsored-view-payment-admin-decision',
                    kwargs={'payment_id': payment.data['id']},
                ),
                {
                    'status': 'verified',
                    'mpesa_transaction_id': 'STARTERSPONSORTXN1',
                    'verification_notes': 'Verified against the authorized development fixture.',
                },
                format='json',
            )
        self.assertEqual(verified.status_code, 200)
        self.client.force_authenticate(self.student)
        with patch(
            'apps.cohorts.sponsored_views.timezone.now',
            return_value=monday + timedelta(minutes=1),
        ):
            started = self.client.post(
                reverse(
                    'sponsored-view-attempt-start',
                    kwargs={'payment_id': payment.data['id']},
                ),
                {},
                format='json',
            )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(len(started.data['questions']), 10)
        self.assertNotIn('correct_answer', started.data['questions'][0])
        answers = self.submit_all_correct(started, SponsoredViewQuestion, self.sponsored)
        with patch(
            'apps.cohorts.sponsored_views.timezone.now',
            return_value=monday + timedelta(minutes=2),
        ):
            submitted = self.client.post(
                reverse(
                    'sponsored-view-attempt-submit',
                    kwargs={'attempt_id': started.data['id']},
                ),
                {'answers': answers},
                format='json',
            )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'graded')
        self.assertEqual(submitted.data['score'], 100)
    def test_main_contest_requires_verified_entitlement_then_starts_and_grades(self):
        friday = eat_datetime(16)
        payment = ParticipationPayment.objects.create(
            user=self.student,
            full_name='Starter Student',
            phone_number='0712345678',
            field='Software Development',
            amount_kes=100,
            till_number='1598106',
            payment_reference='STARTERCONTEST1',
            mpesa_transaction_id='STARTERCONTESTTXN1',
            status='verified',
            expires_at=eat_datetime(19),
        )
        self.assertIsNotNone(payment.id)
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            library = self.client.get(
                reverse('contest-assessment-library'),
                {'field': 'Software Development', 'week': 1},
            )
            self.assertEqual(library.status_code, 200)
            self.assertEqual(library.data['count'], 1)
            self.assertTrue(library.data['results'][0]['can_start'])
            started = self.client.post(
                reverse(
                    'contest-assessment-start',
                    kwargs={'assessment_id': self.contest.id},
                ),
                {},
                format='json',
            )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(len(started.data['questions']), 10)
        self.assertNotIn('correct_answer', started.data['questions'][0])
        answers = self.submit_all_correct(started, AssessmentScheduleQuestion, self.contest)
        with patch(
            'apps.cohorts.programme_views.timezone.now',
            return_value=friday + timedelta(minutes=1),
        ):
            submitted = self.client.post(
                reverse(
                    'contest-assessment-submit',
                    kwargs={'attempt_id': started.data['id']},
                ),
                {'answers': answers},
                format='json',
            )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'graded')
        self.assertEqual(submitted.data['score'], 100)
        with patch(
            'apps.cohorts.programme_views.timezone.now',
            return_value=friday + timedelta(minutes=2),
        ):
            reviewed_library = self.client.get(
                reverse('contest-assessment-library'),
                {'field': 'Software Development', 'week': 1},
            )
        reviewed_questions = reviewed_library.data['results'][0]['attempt']['questions']
        self.assertEqual(len(reviewed_questions), 10)
        self.assertIn('correct_answer', reviewed_questions[0])
        self.assertIn('rationale', reviewed_questions[0])
