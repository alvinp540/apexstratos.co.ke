from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.cohorts.content_validation import (
    contest_is_complete,
    sponsored_view_is_complete,
    tutorial_is_complete,
)
from apps.cohorts.models import AssessmentSchedule, SponsoredViewAssessment, Tutorial
from apps.cohorts.tutorial_schedule import (
    EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS,
    EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS,
    EXPECTED_INITIAL_SPONSORED_ASSESSMENTS,
    EXPECTED_INITIAL_SPONSORED_QUESTIONS,
    EXPECTED_INITIAL_TUTORIALS,
    EXPECTED_INITIAL_QUESTIONS,
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
            fingerprint = tutorial_is_complete(item)
            if fingerprint:
                valid_tutorials.append((item, fingerprint))
        unique_tutorials = {}
        for item, fingerprint in valid_tutorials:
            unique_tutorials.setdefault(fingerprint, item)
        duplicate_tutorials = len(valid_tutorials) - len(unique_tutorials)
        valid_tutorials = list(unique_tutorials.values())
        tutorial_questions = sum(item.questions.count() for item in valid_tutorials)

        contests = list(AssessmentSchedule.objects.prefetch_related('questions'))
        contest_question_records = sum(item.questions.count() for item in contests)
        published_contests = [
            item for item in contests
            if item.status in ('published', 'scheduled')
        ]
        valid_contests = [
            (item, contest_is_complete(item))
            for item in published_contests
        ]
        valid_contests = [(item, fingerprint) for item, fingerprint in valid_contests if fingerprint]
        unique_contests = {}
        for item, fingerprint in valid_contests:
            unique_contests.setdefault(fingerprint, item)
        duplicate_contests = len(valid_contests) - len(unique_contests)
        valid_contests = list(unique_contests.values())
        contest_questions = sum(item.questions.count() for item in valid_contests)

        self.stdout.write(
            f'Tutorial Library: database has {len(tutorials)} assessment records and '
            f'{tutorial_question_records} questions; {len(valid_tutorials)}/'
            f'{EXPECTED_INITIAL_TUTORIALS} complete published assessments and '
            f'{tutorial_questions}/{EXPECTED_INITIAL_QUESTIONS} complete questions '
            f'({duplicate_tutorials} duplicate assessment(s) excluded).'
        )
        sponsored = list(SponsoredViewAssessment.objects.prefetch_related('questions'))
        sponsored_question_records = sum(item.questions.count() for item in sponsored)
        published_sponsored = [item for item in sponsored if item.status == 'published']
        valid_sponsored = [
            (item, sponsored_view_is_complete(item))
            for item in published_sponsored
        ]
        valid_sponsored = [(item, fingerprint) for item, fingerprint in valid_sponsored if fingerprint]
        unique_sponsored = {}
        for item, fingerprint in valid_sponsored:
            unique_sponsored.setdefault(fingerprint, item)
        duplicate_sponsored = len(valid_sponsored) - len(unique_sponsored)
        valid_sponsored = list(unique_sponsored.values())
        sponsored_questions = sum(item.questions.count() for item in valid_sponsored)

        self.stdout.write(
            f'Sponsored View Library: database has {len(sponsored)} assessment records and '
            f'{sponsored_question_records} questions; {len(valid_sponsored)}/'
            f'{EXPECTED_INITIAL_SPONSORED_ASSESSMENTS} complete published assessments and '
            f'{sponsored_questions}/{EXPECTED_INITIAL_SPONSORED_QUESTIONS} complete questions '
            f'({duplicate_sponsored} duplicate assessment(s) excluded).'
        )
        self.stdout.write(
            f'Main Contest Library: database has {len(contests)} assessment records and '
            f'{contest_question_records} questions; {len(valid_contests)}/'
            f'{EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS} complete published assessments and '
            f'{contest_questions}/{EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS} complete questions '
            f'({duplicate_contests} duplicate assessment(s) excluded).'
        )
        self.stdout.write(
            'Media dependencies: none are counted; assessment readiness is based on written content and ten valid MCQs.'
        )

        shortages = []
        if len(valid_tutorials) != EXPECTED_INITIAL_TUTORIALS:
            shortages.append(f'Tutorial Library short by {EXPECTED_INITIAL_TUTORIALS - len(valid_tutorials)} assessments')
        if tutorial_questions != EXPECTED_INITIAL_QUESTIONS:
            shortages.append(f'Tutorial Library short by {EXPECTED_INITIAL_QUESTIONS - tutorial_questions} questions')
        if len(valid_sponsored) != EXPECTED_INITIAL_SPONSORED_ASSESSMENTS:
            shortages.append(f'Sponsored View Library short by {EXPECTED_INITIAL_SPONSORED_ASSESSMENTS - len(valid_sponsored)} assessments')
        if sponsored_questions != EXPECTED_INITIAL_SPONSORED_QUESTIONS:
            shortages.append(f'Sponsored View Library short by {EXPECTED_INITIAL_SPONSORED_QUESTIONS - sponsored_questions} questions')
        if len(valid_contests) != EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS:
            shortages.append(f'Main Contest Library short by {EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS - len(valid_contests)} assessments')
        if contest_questions != EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS:
            shortages.append(f'Main Contest Library short by {EXPECTED_INITIAL_MAIN_CONTEST_QUESTIONS - contest_questions} questions')
        if shortages:
            raise CommandError('; '.join(shortages))
