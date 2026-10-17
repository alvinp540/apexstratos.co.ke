from datetime import timedelta
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.accounts.models import User
from apps.cohorts.models import Tutorial, TutorialAttempt, TutorialProgress, TutorialQuestion
from apps.cohorts.tutorial_schedule import (
    CAPABILITY_FIELDS,
    EXPECTED_INITIAL_QUESTIONS,
    EXPECTED_INITIAL_TUTORIALS,
)


class TutorialCatalogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='tutorial-learner@example.test',
            username='tutorial-learner',
            password='test-password',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def make_tutorial(self, **overrides):
        values = {
            'month': 1,
            'week': 1,
            'day': 0,
            'daily_slot': 1,
            'field': 'Software Development',
            'title': 'API request and response reasoning',
            'description': 'Understand how clients and services exchange data.',
            'learning_objectives': ['Trace a request', 'Interpret a response', 'Handle an error'],
            'concept_explanation': 'An API defines how one software component requests a capability from another.',
            'terminology_and_components': 'A client sends a request to a service endpoint; the endpoint returns a response.',
            'why_it_matters': 'Clear interfaces let independently developed systems cooperate safely.',
            'how_it_works': 'The client selects an endpoint, supplies a method and data, and interprets the response.',
            'worked_examples': 'A profile screen sends a GET request and renders the returned profile fields.',
            'common_mistakes': 'Treating every non-200 response as success hides service and permission errors.',
            'practical_application': 'Inspect request method, URL, payload, response status, and response body while debugging.',
            'decisions_and_tradeoffs': 'Choose a response shape that is stable for clients without returning unnecessary data.',
            'related_concepts': 'Authentication, authorization, serialization, and observability build on the request-response boundary.',
            'difficulty': 'foundation',
            'scheduled_for': timezone.now() - timedelta(days=1),
            'status': 'published',
        }
        values.update(overrides)
        tutorial = Tutorial.objects.create(**values)
        for order in range(1, 11):
            TutorialQuestion.objects.create(
                tutorial=tutorial,
                order=order,
                question_type='multiple_choice',
                prompt=f'In this practical situation, what is the best next step? Case {order}.',
                options=['Inspect the request', 'Ignore the error', 'Repeat blindly', 'Disable validation'],
                correct_answer='Inspect the request',
                rationale='The request context identifies the failure boundary.',
            )
        return tutorial

    def test_catalog_returns_ten_questions_without_answer_keys_or_rationales(self):
        tutorial = self.make_tutorial()

        response = self.client.get(reverse('tutorial-list'))

        self.assertEqual(response.status_code, 200)
        item = response.data['results'][0]
        self.assertEqual(str(item['id']), str(tutorial.id))
        self.assertEqual(len(item['questions']), 10)
        self.assertNotIn('correct_answer', item['questions'][0])
        self.assertNotIn('rationale', item['questions'][0])
        self.assertIn('worked_examples', item)
        self.assertEqual(item['week'], 1)
        self.assertNotIn('video_url', item)

    def test_week_filter_exposes_weeks_five_through_eight(self):
        tutorial = self.make_tutorial(month=2, week=1)

        response = self.client.get(reverse('tutorial-list'), {'week': 5})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(str(response.data['results'][0]['id']), str(tutorial.id))
        self.assertEqual(response.data['results'][0]['week'], 5)

    def test_topic_filter_searches_published_titles_and_descriptions(self):
        tutorial = self.make_tutorial(title='Secure API boundaries')
        self.make_tutorial(
            week=2,
            daily_slot=2,
            title='Practical data modelling',
            description='Reason about entities and their relationships.',
        )

        response = self.client.get(reverse('tutorial-list'), {'topic': 'API'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(str(response.data['results'][0]['id']), str(tutorial.id))

    def test_topic_filter_rejects_overlong_search_terms(self):
        response = self.client.get(reverse('tutorial-list'), {'topic': 'x' * 121})

        self.assertEqual(response.status_code, 400)

    def test_tutorial_attempt_saves_progress_and_preserves_content_for_revision(self):
        tutorial = self.make_tutorial()
        scheduled_time = datetime(2026, 10, 15, 10, tzinfo=ZoneInfo('Africa/Nairobi'))
        with patch('apps.cohorts.views.timezone.now', return_value=scheduled_time):
            started = self.client.post(
                reverse('tutorial-attempt-start', kwargs={'tutorial_id': tutorial.id}),
                {},
                format='json',
            )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(len(started.data['questions']), 10)
        self.assertNotIn('correct_answer', started.data['questions'][0])

        answers = {
            question['id']: 'Inspect the request'
            for question in started.data['questions']
        }
        with patch('apps.cohorts.views.timezone.now', return_value=scheduled_time + timedelta(minutes=1)):
            submitted = self.client.post(
                reverse('tutorial-attempt-submit', kwargs={'attempt_id': started.data['id']}),
                {'answers': answers},
                format='json',
            )
            repeated = self.client.post(
                reverse('tutorial-attempt-submit', kwargs={'attempt_id': started.data['id']}),
                {'answers': answers},
                format='json',
            )

        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['score'], 100)
        self.assertIn('rationale', submitted.data['questions'][0])
        self.assertEqual(repeated.data['score'], 100)
        self.assertEqual(TutorialAttempt.objects.count(), 1)
        progress = TutorialProgress.objects.get(user=self.user, tutorial=tutorial)
        self.assertEqual(progress.attempt_count, 1)
        self.assertEqual(progress.best_score, 100)
        self.assertIsNotNone(progress.completed_at)
        self.assertEqual(tutorial.questions.count(), 10)
        self.assertEqual(Tutorial.objects.count(), 1)

    def test_tutorial_requires_written_reasoning_when_configured(self):
        tutorial = self.make_tutorial()
        tutorial.questions.filter(order=1).update(requires_reasoning=True)
        scheduled_time = datetime(2026, 10, 15, 10, tzinfo=ZoneInfo('Africa/Nairobi'))
        with patch('apps.cohorts.views.timezone.now', return_value=scheduled_time):
            started = self.client.post(
                reverse('tutorial-attempt-start', kwargs={'tutorial_id': tutorial.id}),
                {},
                format='json',
            )
        answers = {question['id']: 'Inspect the request' for question in started.data['questions']}
        submit_url = reverse('tutorial-attempt-submit', kwargs={'attempt_id': started.data['id']})

        with patch('apps.cohorts.views.timezone.now', return_value=scheduled_time + timedelta(minutes=1)):
            missing_reasoning = self.client.post(
                submit_url,
                {'answers': answers},
                format='json',
            )
            submitted = self.client.post(
                submit_url,
                {'answers': answers, 'reasoning': {started.data['questions'][0]['id']: 'The request shows the failing boundary.'}},
                format='json',
            )

        self.assertEqual(missing_reasoning.status_code, 400)
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['questions'][0]['written_reasoning'], 'The request shows the failing boundary.')

    def test_draft_tutorials_are_hidden_but_published_content_has_no_start_appointment(self):
        self.make_tutorial()
        self.make_tutorial(
            week=2,
            status='draft',
            title='Draft content',
        )
        self.make_tutorial(
            week=3,
            scheduled_for=timezone.now() + timedelta(days=1),
            title='Scheduled content',
        )

        response = self.client.get(reverse('tutorial-list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_reading_tutorials_does_not_consume_or_change_content(self):
        tutorial = self.make_tutorial()

        self.client.get(reverse('tutorial-detail', kwargs={'tutorial_id': tutorial.id}))
        self.client.get(reverse('tutorial-list'))
        tutorial.refresh_from_db()

        self.assertEqual(tutorial.status, 'published')
        self.assertEqual(tutorial.questions.count(), 10)
        self.assertEqual(Tutorial.objects.count(), 1)

    def test_tutorial_api_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse('tutorial-list'))

        self.assertEqual(response.status_code, 401)

    def test_students_cannot_write_tutorial_content(self):
        response = self.client.post(reverse('tutorial-list'), {'title': 'Changed by student'})

        self.assertEqual(response.status_code, 405)

    def test_publication_requires_exact_ordered_question_slots(self):
        tutorial = self.make_tutorial(status='draft')
        TutorialQuestion.objects.filter(tutorial=tutorial, order=1).update(order=11)

        with self.assertRaises(ValidationError) as error:
            tutorial.validate_for_publication()

        self.assertIn('questions', error.exception.message_dict)

    def test_sensitive_field_requires_expert_review(self):
        tutorial = self.make_tutorial(field='Medical and Health', status='draft')
        with self.assertRaises(ValidationError) as error:
            tutorial.validate_for_publication()

        self.assertIn('expert_reviewed', error.exception.message_dict)

    def test_complete_tutorial_passes_publication_validation(self):
        tutorial = self.make_tutorial(status='draft')
        tutorial.validate_for_publication()

    def test_initial_curriculum_dimensions_are_fixed(self):
        self.assertEqual(len(CAPABILITY_FIELDS), 10)
        self.assertEqual(EXPECTED_INITIAL_TUTORIALS, 640)
        self.assertEqual(EXPECTED_INITIAL_QUESTIONS, 6400)

    def test_library_audit_reports_missing_content_without_seeding_placeholders(self):
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command('audit_initial_tutorial_library', stdout=output, stderr=output)

        self.assertIn('0/640', output.getvalue())
        self.assertIn('0/6400', output.getvalue())
        self.assertEqual(Tutorial.objects.count(), 0)
