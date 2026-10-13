from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.cohorts.models import (
    AssessmentSchedule,
    Tutorial,
)
from apps.cohorts.tutorial_schedule import CAPABILITY_FIELDS


class Command(BaseCommand):
    help = 'Report verified tutorial and main-contest inventory against ApexStratos targets.'

    def handle(self, *args, **options):
        failures = []
        self._audit_tutorials(failures)
        self._audit_assessments(failures)
        self.stdout.write('Sponsored View: NOT IMPLEMENTED; no persistent programme, video, question, or attempt model exists.')
        self.stdout.write('Sponsored View target: 1,600 videos and 8,000 questions; actual inventory cannot be verified.')

        if failures:
            raise CommandError('; '.join(failures))
        self.stdout.write(self.style.SUCCESS('Tutorial and main-contest inventories meet their stated targets.'))

    def _audit_tutorials(self, failures):
        tutorials = list(Tutorial.objects.prefetch_related('questions').order_by('field', 'month', 'week', 'day', 'daily_slot'))
        videos = sum(self._has_video(tutorial.video) for tutorial in tutorials)
        question_total = 0
        malformed = []
        field_counts = Counter()
        ready_counts = Counter()

        for tutorial in tutorials:
            field_counts[tutorial.field] += 1
            questions = list(tutorial.questions.all())
            question_total += len(questions)
            orders = [question.order for question in questions]
            if orders != [1, 2, 3, 4, 5]:
                malformed.append(str(tutorial.id))
            try:
                tutorial.validate_for_publication()
                content_ready = self._has_video(tutorial.video)
            except ValidationError:
                content_ready = False
            if content_ready and tutorial.status in ('published', 'scheduled'):
                ready_counts[tutorial.field] += 1

        status_counts = Counter(tutorial.status for tutorial in tutorials)
        self.stdout.write(
            f'Free tutorials: {len(tutorials)}/640 records, {videos}/640 internal video files, '
            f'{question_total}/3,200 questions; publication states={dict(status_counts)}.'
        )
        self.stdout.write(f'Tutorials with field assignment other than the ten official areas: {sum(field_counts[field] for field in field_counts if field not in CAPABILITY_FIELDS)}')
        self.stdout.write(f'Tutorials with question orders other than 1-5: {len(malformed)}')

        if len(tutorials) != 640:
            failures.append(f'expected 640 tutorial records, found {len(tutorials)}')
        if videos != 640:
            failures.append(f'expected 640 available tutorial videos, found {videos}')
        if question_total != 3200:
            failures.append(f'expected 3200 tutorial questions, found {question_total}')
        if malformed:
            failures.append(f'{len(malformed)} tutorials do not have exactly five ordered questions')
        for field in CAPABILITY_FIELDS:
            if field_counts[field] != 64:
                failures.append(f'{field}: expected 64 tutorial records, found {field_counts[field]}')
            if ready_counts[field] != 64:
                failures.append(f'{field}: expected 64 complete scheduled or published tutorials, found {ready_counts[field]}')

    def _audit_assessments(self, failures):
        assessments = list(AssessmentSchedule.objects.prefetch_related('questions').order_by('field', 'month', 'week', 'day', 'assessment_slot'))
        videos = sum(self._has_video(assessment.video) for assessment in assessments)
        question_total = 0
        malformed = []
        field_counts = Counter()
        ready_counts = Counter()

        for assessment in assessments:
            field_counts[assessment.field] += 1
            questions = list(assessment.questions.all())
            question_total += len(questions)
            orders = [question.order for question in questions]
            valid_questions = (
                len(questions) == 5
                and orders == [1, 2, 3, 4, 5]
                and all(
                    question.question_type == 'multiple_choice'
                    and isinstance(question.options, list)
                    and len(question.options) >= 2
                    and question.correct_answer in question.options
                    for question in questions
                )
            )
            if not valid_questions:
                malformed.append(str(assessment.id))
            content_ready = (
                self._has_video(assessment.video)
                and valid_questions
                and assessment.duration_minutes == 20
                and isinstance(assessment.learning_objectives, list)
                and len(assessment.learning_objectives) >= 3
            )
            if content_ready and assessment.status in ('published', 'scheduled'):
                ready_counts[assessment.field] += 1

        status_counts = Counter(assessment.status for assessment in assessments)
        self.stdout.write(
            f'Main contests: {len(assessments)}/720 records, {videos}/720 internal video files, '
            f'{question_total}/3,600 questions; publication states={dict(status_counts)}.'
        )
        self.stdout.write(f'Assessments with invalid MCQs, options, keys, or question order: {len(malformed)}')

        if len(assessments) != 720:
            failures.append(f'expected 720 main-contest records, found {len(assessments)}')
        if videos != 720:
            failures.append(f'expected 720 available main-contest videos, found {videos}')
        if question_total != 3600:
            failures.append(f'expected 3600 main-contest questions, found {question_total}')
        if malformed:
            failures.append(f'{len(malformed)} assessments do not have five valid ordered multiple-choice questions')
        for field in CAPABILITY_FIELDS:
            if field_counts[field] != 72:
                failures.append(f'{field}: expected 72 main-contest records, found {field_counts[field]}')
            if ready_counts[field] != 72:
                failures.append(f'{field}: expected 72 complete scheduled or published assessments, found {ready_counts[field]}')

    @staticmethod
    def _has_video(video):
        return bool(video and video.storage.exists(video.name))
