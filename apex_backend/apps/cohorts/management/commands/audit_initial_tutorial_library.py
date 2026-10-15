from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max, Min

from apps.cohorts.models import Tutorial
from apps.cohorts.tutorial_schedule import (
    EXPECTED_INITIAL_QUESTIONS,
    EXPECTED_INITIAL_TUTORIALS,
    INITIAL_MONTHS,
)


class Command(BaseCommand):
    help = 'Verify the initial eight-week text tutorial library and its ten-question assessments.'

    def handle(self, *args, **options):
        tutorials = Tutorial.objects.filter(
            month__gte=1,
            month__lte=INITIAL_MONTHS,
            status='published',
        )
        published_count = tutorials.count()
        question_summary = list(
            tutorials.annotate(
                question_count=Count('questions'),
                first_question=Min('questions__order'),
                last_question=Max('questions__order'),
            ).values('id', 'question_count', 'first_question', 'last_question')
        )
        question_count = sum(row['question_count'] for row in question_summary)
        invalid_question_counts = [
            (row['id'], row['question_count'], row['first_question'], row['last_question'])
            for row in question_summary
            if (row['question_count'], row['first_question'], row['last_question']) != (10, 1, 10)
        ]

        self.stdout.write(
            f'Published tutorials in months 1-{INITIAL_MONTHS}: '
            f'{published_count}/{EXPECTED_INITIAL_TUTORIALS}'
        )
        self.stdout.write(
            f'Tutorial questions: {question_count}/{EXPECTED_INITIAL_QUESTIONS}'
        )
        self.stdout.write(
            f'Tutorials with a question count other than ten: {len(invalid_question_counts)}'
        )

        problems = []
        if published_count != EXPECTED_INITIAL_TUTORIALS:
            problems.append(f'expected {EXPECTED_INITIAL_TUTORIALS} published tutorials')
        if question_count != EXPECTED_INITIAL_QUESTIONS:
            problems.append(f'expected {EXPECTED_INITIAL_QUESTIONS} questions')
        if invalid_question_counts:
            problems.append('every tutorial must have exactly ten ordered questions numbered 1 through 10')
        if problems:
            if invalid_question_counts:
                self.stderr.write(f'Sample invalid tutorial question counts: {invalid_question_counts}')
            raise CommandError('; '.join(problems))

        self.stdout.write(self.style.SUCCESS('Initial eight-week tutorial library is complete and valid.'))
