from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import (
    AssessmentSchedule,
    AssessmentScheduleAttempt,
    AssessmentScheduleQuestion,
    ParticipationPayment,
    Tutorial,
    TutorialAttempt,
    TutorialQuestion,
)
from apps.cohorts.weekly_schedule import (
    activity_status,
    activity_window,
    attempt_deadline,
    next_opening,
    weekly_schedule,
)


EAT = ZoneInfo('Africa/Nairobi')


def eat_datetime(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=EAT)


class WeeklyScheduleRuleTests(TestCase):
    def test_tutorial_window_ends_at_friday_midnight_and_contest_opens_at_same_boundary(self):
        thursday_last_second = eat_datetime(2026, 10, 15, 23, 59, 59)
        friday_start = eat_datetime(2026, 10, 16)

        self.assertIsNotNone(activity_window('tutorials', thursday_last_second))
        self.assertIsNone(activity_window('tutorials', friday_start))
        self.assertIsNone(activity_window('main_contest', thursday_last_second))
        self.assertEqual(
            activity_window('main_contest', friday_start)[0],
            friday_start,
        )
        self.assertEqual(
            attempt_deadline('tutorials', thursday_last_second),
            friday_start,
        )

    def test_contest_window_ends_at_monday_midnight_and_tutorials_open(self):
        sunday_last_second = eat_datetime(2026, 10, 18, 23, 59, 59)
        monday_start = eat_datetime(2026, 10, 19)

        self.assertIsNotNone(activity_window('main_contest', sunday_last_second))
        self.assertIsNone(activity_window('main_contest', monday_start))
        self.assertIsNotNone(activity_window('tutorials', monday_start))
        self.assertEqual(
            attempt_deadline('main_contest', sunday_last_second),
            monday_start,
        )

    def test_weekly_status_returns_next_opening_and_current_boundary(self):
        friday = eat_datetime(2026, 10, 16, 12)

        state = weekly_schedule(friday)

        self.assertEqual(state['timezone'], 'Africa/Nairobi')
        self.assertTrue(state['activities']['main_contest']['available_now'])
        self.assertEqual(
            state['activities']['main_contest']['closes_at'],
            eat_datetime(2026, 10, 19),
        )
        self.assertEqual(
            state['activities']['tutorials']['opens_at'],
            eat_datetime(2026, 10, 19),
        )
        self.assertEqual(
            activity_status('main_contest', friday)['opens_at'],
            eat_datetime(2026, 10, 23),
        )
        self.assertEqual(
            next_opening('tutorials', friday),
            eat_datetime(2026, 10, 19),
        )


class TutorialScheduleAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='weekly-tutorial@example.test',
            username='weekly-tutorial',
            password='test-password',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.tutorial = Tutorial.objects.create(
            month=1,
            week=1,
            day=0,
            daily_slot=1,
            field='Software Development',
            title='Weekly schedule test',
            description='Test content for weekly schedule access.',
            learning_objectives=['Identify', 'Explain', 'Apply'],
            duration_minutes=30,
            concept_explanation='Concept.',
            terminology_and_components='Terminology.',
            why_it_matters='Importance.',
            how_it_works='How it works.',
            worked_examples='Example.',
            common_mistakes='Mistake.',
            practical_application='Application.',
            decisions_and_tradeoffs='Tradeoffs.',
            related_concepts='Related.',
            scheduled_for=eat_datetime(2026, 10, 11),
            status='published',
        )
        for order in range(1, 11):
            TutorialQuestion.objects.create(
                tutorial=self.tutorial,
                order=order,
                question_type='multiple_choice',
                prompt=f'Question {order}',
                options=['A', 'B'],
                correct_answer='A',
            )

    def start(self):
        return self.client.post(
            reverse('tutorial-attempt-start', kwargs={'tutorial_id': self.tutorial.id}),
            {},
            format='json',
        )

    def test_api_blocks_friday_start_but_allows_thursday_until_boundary(self):
        thursday = eat_datetime(2026, 10, 15, 23, 59, 59)
        friday = eat_datetime(2026, 10, 16)
        with patch('apps.cohorts.views.timezone.now', return_value=thursday):
            permitted = self.start()
        with patch('apps.cohorts.views.timezone.now', return_value=friday):
            blocked = self.start()

        self.assertEqual(permitted.status_code, 201)
        self.assertEqual(permitted.data['deadline_at'], eat_datetime(2026, 10, 16))
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(TutorialAttempt.objects.count(), 1)

    def test_tutorial_is_available_without_a_scheduled_start_appointment(self):
        self.tutorial.scheduled_for = eat_datetime(2027, 1, 1)
        self.tutorial.save(update_fields=('scheduled_for',))
        monday = eat_datetime(2026, 10, 12, 10)
        with patch('apps.cohorts.views.timezone.now', return_value=monday):
            listing = self.client.get(reverse('tutorial-list'))
            detail = self.client.get(
                reverse('tutorial-detail', kwargs={'tutorial_id': self.tutorial.id}),
            )
            started = self.start()

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['count'], 1)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(started.status_code, 201)

    def test_tutorial_timer_uses_configured_duration_and_enforces_it_server_side(self):
        started_at = eat_datetime(2026, 10, 12, 10)
        with patch('apps.cohorts.views.timezone.now', return_value=started_at):
            started = self.start()

        self.assertEqual(started.status_code, 201)
        self.assertEqual(
            started.data['deadline_at'],
            started_at + timedelta(minutes=30),
        )
        with patch(
            'apps.cohorts.views.timezone.now',
            return_value=started_at + timedelta(minutes=30),
        ):
            expired = self.client.post(
                reverse('tutorial-attempt-answers', kwargs={'attempt_id': started.data['id']}),
                {'answers': {started.data['questions'][0]['id']: 'A'}, 'reasoning': {}},
                format='json',
            )

        self.assertEqual(expired.status_code, 410)

    def test_resume_uses_same_attempt_and_original_deadline_then_times_out(self):
        started_at = eat_datetime(2026, 10, 15, 10)
        with patch('apps.cohorts.views.timezone.now', return_value=started_at):
            started = self.start()
        question_id = started.data['questions'][0]['id']
        with patch('apps.cohorts.views.timezone.now', return_value=started_at + timedelta(minutes=1)):
            saved = self.client.post(
                reverse('tutorial-attempt-answers', kwargs={'attempt_id': started.data['id']}),
                {'answers': {question_id: 'B'}, 'reasoning': {}},
                format='json',
            )
            resumed = self.start()

        self.assertEqual(started.status_code, 201)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(started.data['id'], resumed.data['id'])
        self.assertEqual(started.data['deadline_at'], resumed.data['deadline_at'])
        self.assertEqual(resumed.data['answers'][question_id], 'B')
        self.assertEqual(TutorialAttempt.objects.count(), 1)

        submit_url = reverse('tutorial-attempt-submit', kwargs={'attempt_id': started.data['id']})
        answers = {item['id']: 'A' for item in started.data['questions']}
        with patch(
            'apps.cohorts.views.timezone.now',
            return_value=eat_datetime(2026, 10, 16),
        ):
            expired = self.client.post(submit_url, {'answers': answers}, format='json')
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(TutorialAttempt.objects.get().status, 'timed_out')
        with patch(
            'apps.cohorts.views.timezone.now',
            return_value=eat_datetime(2026, 10, 19, 10),
        ):
            restart = self.start()
        self.assertEqual(restart.status_code, 409)
        self.assertEqual(TutorialAttempt.objects.count(), 1)

    def test_graded_result_remains_readable_and_cannot_be_restarted(self):
        monday = eat_datetime(2026, 10, 12, 10)
        with patch('apps.cohorts.views.timezone.now', return_value=monday):
            started = self.start()
        answers = {item['id']: 'A' for item in started.data['questions']}
        submit_url = reverse('tutorial-attempt-submit', kwargs={'attempt_id': started.data['id']})
        with patch('apps.cohorts.views.timezone.now', return_value=monday + timedelta(minutes=1)):
            submitted = self.client.post(submit_url, {'answers': answers}, format='json')
            restarted = self.start()

        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(restarted.status_code, 200)
        self.assertEqual(restarted.data['status'], 'graded')
        self.assertEqual(restarted.data['score'], 100)
        self.assertEqual(TutorialAttempt.objects.count(), 1)

        with patch('apps.cohorts.views.timezone.now', return_value=eat_datetime(2026, 10, 16)):
            detail = self.client.get(reverse('tutorial-detail', kwargs={'tutorial_id': self.tutorial.id}))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['current_attempt']['status'], 'graded')
        self.assertIn('correct_answer', detail.data['current_attempt']['questions'][0])

    def test_schedule_endpoint_uses_eat_weekday(self):
        with patch(
            'apps.cohorts.weekly_schedule.timezone.now',
            return_value=eat_datetime(2026, 10, 16, 0),
        ):
            response = self.client.get(reverse('weekly-schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['weekday'], 'Friday')
        self.assertFalse(response.data['activities']['tutorials']['available_now'])
        self.assertTrue(response.data['activities']['main_contest']['available_now'])


class MainContestScheduleAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='weekly-contest@example.test',
            username='weekly-contest',
            password='test-password',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.assessment = AssessmentSchedule.objects.create(
            month=1,
            week=1,
            day=4,
            assessment_slot=1,
            field='Software Development',
            title='Weekly contest schedule test',
            description='Contest access test.',
            scheduled_for=eat_datetime(2026, 10, 12),
            status='published',
            duration_minutes=20,
        )
        for order in range(1, 11):
            AssessmentScheduleQuestion.objects.create(
                assessment=self.assessment,
                order=order,
                question_type='multiple_choice',
                prompt=f'Contest question {order}',
                options=['A', 'B'],
                correct_answer='A',
            )
        ParticipationPayment.objects.create(
            user=self.user,
            field='Software Development',
            amount_kes=100,
            payment_reference='WEEKLYCONTEST1',
            mpesa_transaction_id='WEEKLYCONFIRM1',
            status='verified',
            expires_at=eat_datetime(2026, 10, 26),
        )

    def start(self):
        return self.client.post(
            reverse('contest-assessment-start', kwargs={'assessment_id': self.assessment.id}),
            {},
            format='json',
        )

    def test_contest_start_is_denied_until_friday_eat_then_deadline_is_server_created(self):
        thursday = eat_datetime(2026, 10, 15, 23, 59, 59)
        friday = eat_datetime(2026, 10, 16)
        with patch('apps.cohorts.programme_views.timezone.now', return_value=thursday):
            too_early = self.start()
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            started = self.start()
        answer_question_id = started.data['questions'][0]['id']
        with patch(
            'apps.cohorts.programme_views.timezone.now',
            return_value=friday + timedelta(minutes=1),
        ):
            saved = self.client.post(
                reverse('contest-assessment-answers', kwargs={'attempt_id': started.data['id']}),
                {'answers': {answer_question_id: 'B'}, 'reasoning': {}},
                format='json',
            )
            resumed = self.start()

        self.assertEqual(too_early.status_code, 403)
        self.assertEqual(started.status_code, 201)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.data['id'], started.data['id'])
        self.assertEqual(resumed.data['answers'][answer_question_id], 'B')
        self.assertEqual(started.data['started_at'], friday)
        self.assertEqual(
            started.data['deadline_at'],
            friday + timedelta(minutes=20),
        )
        self.assertEqual(AssessmentScheduleAttempt.objects.count(), 1)

    def test_sunday_attempt_cannot_continue_past_monday_eat_deadline(self):
        sunday = eat_datetime(2026, 10, 18, 23, 50)
        monday = eat_datetime(2026, 10, 19)
        with patch('apps.cohorts.programme_views.timezone.now', return_value=sunday):
            started = self.start()

        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.data['deadline_at'], monday)
        answer_question_id = started.data['questions'][0]['id']
        with patch('apps.cohorts.programme_views.timezone.now', return_value=monday):
            response = self.client.post(
                reverse('contest-assessment-answers', kwargs={'attempt_id': started.data['id']}),
                {'answers': {answer_question_id: 'A'}, 'reasoning': {}},
                format='json',
            )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            AssessmentScheduleAttempt.objects.get().status,
            'timed_out',
        )
