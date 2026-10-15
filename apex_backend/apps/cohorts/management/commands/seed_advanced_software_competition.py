from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cohorts.models import Assessment, Cohort, Question


QUESTIONS = [
    {
        'text': 'A backend service and frontend client disagree about a response shape. What is the strongest first step?',
        'options': [
            'Define and version a shared API contract, then test both sides against it.',
            'Change the frontend until the error disappears without documenting the contract.',
            'Disable validation on the backend.',
            'Ask users to refresh until the response works.',
        ],
        'correct_answer': 'Define and version a shared API contract, then test both sides against it.',
    },
    {
        'text': 'A production page is slow because it waits on several independent API calls. Which improvement is usually best?',
        'options': [
            'Load every request sequentially on the main thread.',
            'Measure the bottleneck, parallelize independent work, and cache safe results.',
            'Remove error handling from the page.',
            'Increase every timeout without measuring latency.',
        ],
        'correct_answer': 'Measure the bottleneck, parallelize independent work, and cache safe results.',
    },
    {
        'text': 'A security review finds that a user can access another user’s record by changing an ID in the URL. What is missing?',
        'options': [
            'Server-side authorization and object-level access checks.',
            'A brighter button color.',
            'A longer frontend loading animation.',
            'A second browser tab.',
        ],
        'correct_answer': 'Server-side authorization and object-level access checks.',
    },
    {
        'text': 'A release changes database fields used by an active frontend. Which deployment approach reduces risk?',
        'options': [
            'Deploy a backward-compatible schema change before switching clients.',
            'Delete the old field before releasing the new client.',
            'Skip migrations and edit production records manually.',
            'Release without monitoring or rollback steps.',
        ],
        'correct_answer': 'Deploy a backward-compatible schema change before switching clients.',
    },
    {
        'text': 'What best demonstrates successful participation in this advanced competition?',
        'options': [
            'A working solution supported by tests, clear reasoning, and measured improvement.',
            'A high score achieved by submitting before reading the problem.',
            'A screenshot with no reproducible result.',
            'A solution that disables the failing test.',
        ],
        'correct_answer': 'A working solution supported by tests, clear reasoning, and measured improvement.',
    },
    {
        'text': 'A service intermittently returns stale records after a write. Which evidence should guide the first investigation?',
        'options': [
            'Trace the write and read paths, cache invalidation, and consistency guarantees.',
            'Increase the client-side animation duration.',
            'Disable all cache headers without measuring their effect.',
            'Retry the request indefinitely from every client.',
        ],
        'correct_answer': 'Trace the write and read paths, cache invalidation, and consistency guarantees.',
    },
    {
        'text': 'A team proposes storing an authorization role only in a browser-controlled field. What is the key risk?',
        'options': [
            'A client can modify the field, so the server must make the authorization decision.',
            'The browser will render the field in the wrong font.',
            'The role will always be hidden from administrators.',
            'The database will automatically encrypt the field.',
        ],
        'correct_answer': 'A client can modify the field, so the server must make the authorization decision.',
    },
    {
        'text': 'A database migration must add a required field while old and new application versions overlap. What is the safest sequence?',
        'options': [
            'Add it compatibly, backfill, deploy code using it, then enforce the constraint.',
            'Make it non-null immediately and let old writes fail.',
            'Delete existing rows before deploying the new version.',
            'Skip the migration and edit production schema manually.',
        ],
        'correct_answer': 'Add it compatibly, backfill, deploy code using it, then enforce the constraint.',
    },
    {
        'text': 'A model evaluation shows high overall accuracy but poor results for a small subgroup. What should happen next?',
        'options': [
            'Investigate subgroup metrics and data quality before deployment.',
            'Ignore subgroup results because aggregate accuracy is high.',
            'Remove the subgroup from the test set.',
            'Deploy first and collect no further evidence.',
        ],
        'correct_answer': 'Investigate subgroup metrics and data quality before deployment.',
    },
    {
        'text': 'A release improves latency but increases the error rate for one critical operation. Which decision is best?',
        'options': [
            'Compare impact against the service objectives and roll back or mitigate if the objective is breached.',
            'Keep the release because average latency improved.',
            'Hide the error metric from the dashboard.',
            'Increase the timeout and stop investigating.',
        ],
        'correct_answer': 'Compare impact against the service objectives and roll back or mitigate if the objective is breached.',
    },
]


class Command(BaseCommand):
    help = 'Create the shared 30-day advanced software engineering competition cohort.'

    def handle(self, *args, **options):
        now = timezone.now()
        cohort, created = Cohort.objects.get_or_create(
            title='Month 1 Advanced Software Engineering Competition',
            defaults={
                'profession': 'software_engineering',
                'level': 'advanced',
                'payment_tier': '1000kes',
                'description': 'A 30-day cross-functional competition for backend, frontend, data, DevOps, QA, and cybersecurity professionals.',
                'start_date': now,
                'end_date': now + timedelta(days=30),
                'max_participants': 100,
                'assessment_unlock_threshold': 20,
                'status': 'open',
            },
        )
        cohort.profession = 'software_engineering'
        cohort.level = 'advanced'
        cohort.payment_tier = '1000kes'
        cohort.description = 'A 30-day cross-functional competition for backend, frontend, data, DevOps, QA, and cybersecurity professionals.'
        cohort.start_date = cohort.start_date or now
        cohort.end_date = cohort.start_date + timedelta(days=30)
        cohort.max_participants = 100
        cohort.assessment_unlock_threshold = 20
        cohort.status = 'open'
        cohort.save(update_fields=['profession', 'level', 'payment_tier', 'description', 'start_date', 'end_date', 'max_participants', 'assessment_unlock_threshold', 'status'])
        assessment, assessment_created = Assessment.objects.get_or_create(
            cohort=cohort,
            title='Advanced Software Engineering Competition Assessment',
            defaults={
                'instructions': 'Use the scenario details, technical evidence, and stated constraints to select the strongest response.',
                'time_limit_minutes': 30,
                'difficulty': 'expert',
                'passing_score': 70,
                'is_active': True,
            },
        )
        if assessment_created:
            for index, item in enumerate(QUESTIONS):
                Question.objects.create(
                    assessment=assessment,
                    question_type='mcq',
                    text=item['text'],
                    options=item['options'],
                    correct_answer=item['correct_answer'],
                    points=2,
                    order=index,
                )
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Found'} {cohort.title}; "
            f"{'created' if assessment_created else 'kept'} assessment."
        ))
