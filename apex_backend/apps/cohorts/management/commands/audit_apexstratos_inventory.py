from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.cohorts.models import AssessmentSchedule, Tutorial
from apps.cohorts.tutorial_schedule import (
    EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS,
    EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS,
    EXPECTED_INITIAL_SPONSORED_ASSESSMENTS,
    EXPECTED_INITIAL_SPONSORED_QUESTIONS,
    EXPECTED_INITIAL_TUTORIALS,
    EXPECTED_INITIAL_QUESTIONS,
)


def _has_ten_valid_mcqs(assessment):
    questions = list(assessment.questions.order_by('order'))
    return (
        len(questions) == 10
        and [question.order for question in questions] == list(range(1, 11))
        and all(
            question.question_type == 'multiple_choice'
            and isinstance(question.options, list)
            and len(question.options) >= 2
            and question.correct_answer in question.options
            for question in questions
        )
    )


class Command(BaseCommand):
    help = 'Audit actual initial question-library quantities and publication readiness.'

    def handle(self, *args, **options):
        tutorials = list(Tutorial.objects.prefetch_related('questions'))
        tutorial_question_records = sum(item.questions.count() for item in tutorials)
        published_tutorials = [
            item for item in tutorials
            if item.status in ('published', 'scheduled')
        ]
        valid_tutorials = []
        for item in published_tutorials:
            try:
                item.validate_for_publication()
            except ValidationError:
                continue
            valid_tutorials.append(item)
        tutorial_questions = sum(item.questions.count() for item in valid_tutorials)

        contests = list(AssessmentSchedule.objects.prefetch_related('questions'))
        contest_question_records = sum(item.questions.count() for item in contests)
        published_contests = [
            item for item in contests
            if item.status in ('published', 'scheduled')
        ]
        valid_contests = [
            item for item in published_contests
            if item.duration_minutes == 20
            and _has_ten_valid_mcqs(item)
            and isinstance(item.learning_objectives, list)
            and len(item.learning_objectives) >= 3
        ]
        contest_questions = sum(item.questions.count() for item in valid_contests)

        self.stdout.write(
            f'Tutorial Library: database has {len(tutorials)} assessment records and '
            f'{tutorial_question_records} questions; {len(valid_tutorials)}/'
            f'{EXPECTED_INITIAL_TUTORIALS} complete published assessments and '
            f'{tutorial_questions}/{EXPECTED_INITIAL_QUESTIONS} complete questions.'
        )
        self.stdout.write(
            f'Sponsored View Library: 0/{EXPECTED_INITIAL_SPONSORED_ASSESSMENTS} '
            f'complete assessments; 0/{EXPECTED_INITIAL_SPONSORED_QUESTIONS} questions '
            f'(programme models/content are not implemented).'
        )
        self.stdout.write(
            f'Main Contest Library: database has {len(contests)} assessment records and '
            f'{contest_question_records} questions; {len(valid_contests)}/'
            f'{EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS} complete published assessments and '
            f'{contest_questions}/{EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS} complete questions.'
        )
        self.stdout.write(
            'Media dependencies: none are counted; assessment readiness is based on written content and ten valid MCQs.'
        )

        shortages = []
        if len(valid_tutorials) != EXPECTED_INITIAL_TUTORIALS:
            shortages.append(f'Tutorial Library short by {EXPECTED_INITIAL_TUTORIALS - len(valid_tutorials)} assessments')
        if tutorial_questions != EXPECTED_INITIAL_QUESTIONS:
            shortages.append(f'Tutorial Library short by {EXPECTED_INITIAL_QUESTIONS - tutorial_questions} questions')
        if len(valid_contests) != EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS:
            shortages.append(f'Main Contest Library short by {EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS - len(valid_contests)} assessments')
        if contest_questions != EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS:
            shortages.append(f'Main Contest Library short by {EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS - contest_questions} questions')
        shortages.append(f'Sponsored View Library short by {EXPECTED_INITIAL_SPONSORED_ASSESSMENTS} assessments and {EXPECTED_INITIAL_SPONSORED_QUESTIONS} questions')
        if shortages:
            raise CommandError('; '.join(shortages))
