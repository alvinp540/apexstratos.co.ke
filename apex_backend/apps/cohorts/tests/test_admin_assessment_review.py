from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.cohorts.models import Tutorial, TutorialQuestion


class AdminAssessmentReviewTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='content-admin@example.test',
            username='content-admin',
            password='test-password',
            role='admin',
        )
        self.learner = User.objects.create_user(
            email='content-learner@example.test',
            username='content-learner',
            password='test-password',
        )
        self.client.force_authenticate(self.admin)

    def make_tutorial(self, **overrides):
        values = {
            'month': 1,
            'week': 1,
            'day': 0,
            'daily_slot': 1,
            'field': 'Software Development',
            'title': 'Reviewable tutorial',
            'description': 'A complete lesson for administrator review.',
            'learning_objectives': ['Trace a request', 'Read a response', 'Handle a failure'],
            'concept_explanation': 'An interface defines how software components exchange information.',
            'terminology_and_components': 'A client sends a request to a service.',
            'why_it_matters': 'Reliable interfaces let separate systems work together.',
            'how_it_works': 'The client sends a request and interprets the response.',
            'worked_examples': 'A page loads its profile through an API.',
            'common_mistakes': 'Ignoring an error response can conceal a failed request.',
            'practical_application': 'Inspect the method, URL, payload, and response.',
            'decisions_and_tradeoffs': 'Choose a stable and appropriately narrow response shape.',
            'related_concepts': 'Authentication and validation protect the interface.',
            'scheduled_for': timezone.now() - timedelta(days=1),
            'status': 'draft',
        }
        values.update(overrides)
        tutorial = Tutorial.objects.create(**values)
        for order in range(1, 11):
            TutorialQuestion.objects.create(
                tutorial=tutorial,
                order=order,
                question_type='multiple_choice',
                prompt=f'Which action is appropriate for case {order}?',
                options=['Inspect the response', 'Ignore the result', 'Disable checks', 'Retry blindly'],
                correct_answer='Inspect the response',
                rationale='Reviewing the response identifies the outcome.',
            )
        return tutorial

    def test_review_api_is_restricted_to_admins(self):
        self.client.force_authenticate(self.learner)

        response = self.client.get(reverse('admin-assessment-review-list'))

        self.assertEqual(response.status_code, 403)

    def test_admin_can_inspect_answer_key_and_complete_review_workflow(self):
        tutorial = self.make_tutorial()
        list_response = self.client.get(reverse('admin-assessment-review-list'))

        self.assertEqual(list_response.status_code, 200)
        item = list_response.data['results'][0]
        self.assertEqual(item['id'], str(tutorial.id))
        self.assertEqual(item['questions'][0]['correct_answer'], 'Inspect the response')
        self.assertEqual(item['quality_errors'], [])

        action_url = reverse(
            'admin-assessment-review-action',
            kwargs={'library': 'tutorials', 'content_id': tutorial.id},
        )
        submitted = self.client.post(action_url, {'action': 'submit_for_review'}, format='json')
        approved = self.client.post(action_url, {'action': 'approve'}, format='json')
        published = self.client.post(action_url, {'action': 'publish'}, format='json')

        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'in_review')
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data['status'], 'approved')
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.data['status'], 'published')
        tutorial.refresh_from_db()
        self.assertEqual(tutorial.reviewed_by, self.admin)
        self.assertIsNotNone(tutorial.published_at)

    def test_admin_cannot_submit_incomplete_tutorial_for_review(self):
        tutorial = self.make_tutorial(title='')
        action_url = reverse(
            'admin-assessment-review-action',
            kwargs={'library': 'tutorials', 'content_id': tutorial.id},
        )

        response = self.client.post(action_url, {'action': 'submit_for_review'}, format='json')

        self.assertEqual(response.status_code, 400)
        tutorial.refresh_from_db()
        self.assertEqual(tutorial.status, 'draft')

    def test_sensitive_tutorial_requires_expert_review_before_approval(self):
        tutorial = self.make_tutorial(field='Medical and Health')
        action_url = reverse(
            'admin-assessment-review-action',
            kwargs={'library': 'tutorials', 'content_id': tutorial.id},
        )
        submitted = self.client.post(action_url, {'action': 'submit_for_review'}, format='json')
        approval = self.client.post(action_url, {'action': 'approve'}, format='json')

        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(approval.status_code, 400)
        self.assertIn('Qualified expert review is required', approval.data['detail'])
