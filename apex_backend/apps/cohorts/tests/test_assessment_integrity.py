from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from apps.cohorts.views import _grade


class AssessmentScoringTests(TestCase):
    def setUp(self):
        self.question_id = str(uuid4())
        self.question = SimpleNamespace(
            id=self.question_id,
            points=1,
            correct_answer='b',
        )
        self.attempt = SimpleNamespace(
            assessment=SimpleNamespace(
                questions=SimpleNamespace(all=lambda: [self.question]),
            ),
            question_order=[self.question_id],
            answers={self.question_id: 'a'},
            video_watched_seconds=0,
        )

    def test_client_reported_video_time_does_not_change_score(self):
        score_without_claimed_video = _grade(self.attempt)
        self.attempt.video_watched_seconds = 1200
        self.attempt.video_completed = True

        self.assertEqual(_grade(self.attempt), score_without_claimed_video)
        self.assertEqual(score_without_claimed_video, 0)

    def test_score_is_based_on_server_question_answers(self):
        self.attempt.answers = {self.question_id: 'b'}

        self.assertEqual(_grade(self.attempt), 100)

    def test_questions_outside_server_issued_order_are_not_graded(self):
        self.attempt.question_order = []
        self.attempt.answers = {self.question_id: 'b'}

        self.assertEqual(_grade(self.attempt), 0)
