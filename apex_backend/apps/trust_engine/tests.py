from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.trust_engine.engine import calculate_psp_consistency


class MeritConsistencyTests(SimpleTestCase):
    @patch('apps.cohorts.models.AssessmentAttempt.objects.filter')
    def test_consistency_uses_unique_weeks_of_verified_performance(self, filter_attempts):
        filter_attempts.return_value.values_list.return_value = [
            datetime(2026, 9, 1, tzinfo=datetime_timezone.utc),
            datetime(2026, 9, 3, tzinfo=datetime_timezone.utc),
            datetime(2026, 9, 8, tzinfo=datetime_timezone.utc),
        ]
        user = SimpleNamespace(subscription=SimpleNamespace(plan='free', status='active'))

        result = calculate_psp_consistency(user)

        self.assertEqual(result, round((2 / 12) * 100, 2))
        filter_attempts.assert_called_once()
        self.assertEqual(filter_attempts.call_args.kwargs['is_flagged'], False)
        self.assertEqual(filter_attempts.call_args.kwargs['status'], 'graded')

    @patch('apps.cohorts.models.AssessmentAttempt.objects.filter')
    def test_subscription_plan_does_not_change_consistency_merit(self, filter_attempts):
        filter_attempts.return_value.values_list.return_value = [
            datetime(2026, 9, 1, tzinfo=datetime_timezone.utc),
        ]
        user = SimpleNamespace(subscription=SimpleNamespace(plan='elite', status='active'))

        self.assertEqual(calculate_psp_consistency(user), round((1 / 12) * 100, 2))
