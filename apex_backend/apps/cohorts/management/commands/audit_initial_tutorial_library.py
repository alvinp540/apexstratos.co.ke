from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max, Min

from apps.cohorts.models import Tutorial
from apps.cohorts.tutorial_schedule import (
    EXPECTED_INITIAL_QUESTIONS,
    EXPECTED_INITIAL_TUTORIALS,
    INITIAL_MONTHS,
)


class Command(BaseCommand):
    help = 'Verify that months 1-2 contain exactly 640 published internal videos and 3,200 tutorial questions.'

    def handle(self, *args, **options):
        tutorials = Tutorial.objects.filter(month__gte=1, month__lte=INITIAL_MONTHS, status='published')
        published_tutorials = list(tutorials)
        published_count = len(published_tutorials)
        video_count = 0
        for tutorial in published_tutorials:
            if tutorial.video and tutorial.video.storage.exists(tutorial.video.name):
                video_count += 1
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
            if (row['question_count'], row['first_question'], row['last_question']) != (5, 1, 5)
        ][:20]
        missing_video_count = published_count - video_count

        self.stdout.write(f'Published tutorials in months 1-{INITIAL_MONTHS}: {published_count}/{EXPECTED_INITIAL_TUTORIALS}')
        self.stdout.write(f'Internal video files: {video_count}/{EXPECTED_INITIAL_TUTORIALS}')
        self.stdout.write(f'Tutorial questions: {question_count}/{EXPECTED_INITIAL_QUESTIONS}')
        self.stdout.write(f'Tutorials with a question count other than five: {len(invalid_question_counts)}')
        self.stdout.write(f'Published tutorials missing video files: {missing_video_count}')

        problems = []
        if published_count != EXPECTED_INITIAL_TUTORIALS:
            problems.append(f'expected {EXPECTED_INITIAL_TUTORIALS} published tutorials')
        if video_count != EXPECTED_INITIAL_TUTORIALS:
            problems.append(f'expected {EXPECTED_INITIAL_TUTORIALS} uploaded internal videos')
        if question_count != EXPECTED_INITIAL_QUESTIONS:
            problems.append(f'expected {EXPECTED_INITIAL_QUESTIONS} questions')
        if invalid_question_counts:
            problems.append('every tutorial must have ordered question slots 1 through 5')
        if missing_video_count:
            problems.append('every published tutorial must have its internal video uploaded')
        if problems:
            if invalid_question_counts:
                self.stderr.write(f'Sample invalid tutorial question counts: {invalid_question_counts}')
            raise CommandError('; '.join(problems))

        self.stdout.write(self.style.SUCCESS('Initial two-month tutorial library is complete and valid.'))
