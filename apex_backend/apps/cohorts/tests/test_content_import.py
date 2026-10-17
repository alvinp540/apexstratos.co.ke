import copy
import json
from io import StringIO
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cohorts.models import (
    AssessmentSchedule,
    AssessmentScheduleQuestion,
    ParticipationPayment,
    SponsoredViewAssessment,
    SponsoredViewAttempt,
    SponsoredViewPayment,
    SponsoredViewQuestion,
    Tutorial,
    TutorialAttempt,
    TutorialQuestion,
    TutorialProgress,
)


class AssessmentImportTests(TestCase):
    def make_pack(self):
        questions = [
            {
                'order': order,
                'prompt': f'In scenario {order}, which action best verifies the API response contract?',
                'options': [
                    'Check a contract test against the documented schema.',
                    'Remove the response validation.',
                    'Retry until the response looks correct.',
                    'Change the client to ignore every field.',
                ],
                'correct_answer': 'Check a contract test against the documented schema.',
                'rationale': (
                    'A contract test checks the response against the agreed schema and catches '
                    'incompatible changes at the boundary.'
                ),
            }
            for order in range(1, 11)
        ]
        assessment = {
            'external_id': 'software-api-contract-week-1',
            'week': 1,
            'day': 0,
            'slot': 1,
            'field': 'Software Development',
            'title': 'Testing an API contract',
            'description': 'Learn to verify an interface contract before assessing a change.',
            'learning_objectives': [
                'Identify a response contract.',
                'Choose a suitable compatibility check.',
                'Explain the evidence produced by a contract test.',
            ],
            'concept_explanation': 'An API contract defines the observable request and response shape.',
            'terminology_and_components': 'A schema describes fields, types, required values, and constraints.',
            'why_it_matters': 'A shared contract helps independently developed clients and services interoperate.',
            'how_it_works': 'A test sends a representative request and checks the response against the contract.',
            'worked_examples': 'A test can reject a response that omits a required identifier.',
            'common_mistakes': 'Disabling validation hides the disagreement instead of fixing it.',
            'practical_application': 'Run contract tests in continuous integration before deployment.',
            'decisions_and_tradeoffs': 'Versioning can preserve compatibility while clients migrate.',
            'related_concepts': 'Schema evolution and consumer-driven contract testing are related practices.',
            'questions': questions,
        }
        return {
            'schema_version': 1,
            'provenance': {
                'title': 'Original test material',
                'author': 'ApexStratos automated test fixture',
                'license': 'Test-only',
                'attribution': 'Synthetic fixture content created exclusively for automated tests.',
                'reference': 'apps/cohorts/tests/test_content_import.py',
            },
            'assessments': [assessment],
        }

    def run_import(self, payload, *extra_args, library='tutorials'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'content.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            output = tempfile.SpooledTemporaryFile(mode='w+')
            try:
                call_command(
                    'import_apexstratos_assessments',
                    '--library',
                    library,
                    '--file',
                    str(path),
                    *extra_args,
                    stdout=output,
                )
                output.seek(0)
                return output.read()
            finally:
                output.close()

    def test_dry_run_validates_without_writing(self):
        output = self.run_import(self.make_pack())

        self.assertIn('Would create 1 tutorials assessment(s) as drafts', output)
        self.assertEqual(Tutorial.objects.count(), 0)

    def test_apply_is_append_only_idempotent_and_preserves_source(self):
        pack = self.make_pack()
        first = self.run_import(pack, '--apply')
        second = self.run_import(pack, '--apply')

        self.assertIn('Created 1 tutorials assessment(s) as drafts', first)
        self.assertIn('Created 0 tutorials assessment(s) as drafts', second)
        self.assertEqual(Tutorial.objects.count(), 1)
        tutorial = Tutorial.objects.get()
        self.assertEqual(tutorial.status, 'draft')
        self.assertEqual(tutorial.imported_external_id, 'software-api-contract-week-1')
        self.assertEqual(tutorial.content_license, 'Test-only')
        self.assertIn('apps/cohorts/tests/test_content_import.py', tutorial.content_source)
        self.assertEqual(TutorialQuestion.objects.filter(tutorial=tutorial).count(), 10)

    def test_sponsored_view_pack_imports_mcq_questions_without_type_field(self):
        pack = self.make_pack()
        assessment = pack['assessments'][0]
        assessment.pop('day')
        for field in (
            'concept_explanation', 'terminology_and_components', 'why_it_matters',
            'how_it_works', 'worked_examples', 'common_mistakes',
            'practical_application', 'decisions_and_tradeoffs', 'related_concepts',
        ):
            assessment.pop(field)
        assessment['slot'] = 1

        self.run_import(pack, '--apply', library='sponsored-view')

        imported = SponsoredViewAssessment.objects.get()
        self.assertEqual(imported.status, 'draft')
        self.assertEqual(SponsoredViewQuestion.objects.filter(assessment=imported).count(), 10)

    def test_main_contest_pack_imports_timed_assessment_and_ten_questions(self):
        pack = self.make_pack()
        assessment = pack['assessments'][0]
        for field in (
            'concept_explanation', 'terminology_and_components', 'why_it_matters',
            'how_it_works', 'worked_examples', 'common_mistakes',
            'practical_application', 'decisions_and_tradeoffs', 'related_concepts',
        ):
            assessment.pop(field)
        assessment['day'] = 4
        assessment['slot'] = 1

        self.run_import(pack, '--apply', library='main-contest')

        imported = AssessmentSchedule.objects.get()
        self.assertEqual(imported.status, 'draft')
        self.assertEqual(imported.duration_minutes, 20)
        self.assertEqual(AssessmentScheduleQuestion.objects.filter(assessment=imported).count(), 10)

    def test_reimport_with_changed_content_does_not_overwrite_existing_record(self):
        pack = self.make_pack()
        self.run_import(pack, '--apply')
        changed = self.make_pack()
        changed['assessments'][0]['questions'][0]['prompt'] = 'Different question content.'

        with self.assertRaisesRegex(CommandError, 'It was not overwritten'):
            self.run_import(changed, '--apply')

        self.assertEqual(TutorialQuestion.objects.count(), 10)
        self.assertNotEqual(
            TutorialQuestion.objects.order_by('order').first().prompt,
            'Different question content.',
        )

    def test_pack_rejects_invalid_options_rationales_and_placeholder_content(self):
        pack = self.make_pack()
        pack['assessments'][0]['questions'][0]['options'] = ['A', 'B']
        pack['assessments'][0]['questions'][1]['rationale'] = ''
        pack['assessments'][0]['questions'][2]['prompt'] = 'Sample question text here'

        with self.assertRaisesRegex(CommandError, 'exactly four distinct'):
            self.run_import(pack)

        self.assertEqual(Tutorial.objects.count(), 0)

    def test_pack_rejects_duplicate_assessment_question_sets(self):
        pack = self.make_pack()
        duplicate = dict(pack['assessments'][0])
        duplicate.update({
            'external_id': 'software-api-contract-week-1-duplicate',
            'day': 1,
            'slot': 2,
            'title': 'A second title cannot disguise a duplicate assessment',
        })
        pack['assessments'].append(duplicate)

        with self.assertRaisesRegex(CommandError, 'duplicates a complete assessment question set'):
            self.run_import(pack)

        self.assertEqual(Tutorial.objects.count(), 0)

    def test_pack_rejects_repeated_prompts_across_assessments(self):
        pack = self.make_pack()
        duplicate = copy.deepcopy(pack['assessments'][0])
        duplicate.update({
            'external_id': 'software-api-contract-week-1-repeated-prompt',
            'day': 1,
            'slot': 2,
            'title': 'A distinct assessment with one repeated prompt',
        })
        for question in duplicate['questions'][1:]:
            question['prompt'] = 'A distinct scenario asks: ' + question['prompt']
        pack['assessments'].append(duplicate)

        with self.assertRaisesRegex(CommandError, 'duplicates a question in assessments'):
            self.run_import(pack)

        self.assertEqual(Tutorial.objects.count(), 0)

    def test_importer_never_publishes_directly_from_a_pack(self):
        pack = self.make_pack()

        with self.assertRaisesRegex(CommandError, 'unrecognized arguments: --publish'):
            self.run_import(pack, '--apply', '--publish')

        self.assertEqual(Tutorial.objects.count(), 0)

    def test_pack_cannot_set_human_expert_review(self):
        pack = self.make_pack()
        pack['assessments'][0]['expert_reviewed'] = True

        with self.assertRaisesRegex(CommandError, 'only an administrator can record human expert review'):
            self.run_import(pack)

        self.assertEqual(Tutorial.objects.count(), 0)

    def test_bootstrap_rejects_duplicate_bundle_without_writing_records(self):
        with self.assertRaisesRegex(CommandError, 'failed validation'):
            call_command('bootstrap_apexstratos_libraries', stdout=StringIO())

        self.assertEqual(Tutorial.objects.count(), 0)
        self.assertEqual(SponsoredViewAssessment.objects.count(), 0)
        self.assertEqual(AssessmentSchedule.objects.count(), 0)

    def test_inventory_audit_excludes_duplicate_contest_assessment_content(self):
        for slot in (1, 2):
            assessment = AssessmentSchedule.objects.create(
                month=1,
                week=1,
                day=4,
                assessment_slot=slot,
                field='Software Development',
                title=f'Unique title {slot}',
                description=f'Different presentation {slot}.',
                learning_objectives=['Identify', 'Compare', 'Choose'],
                scheduled_for=timezone.now(),
                duration_minutes=20,
                status='published',
            )
            for order in range(1, 11):
                AssessmentScheduleQuestion.objects.create(
                    assessment=assessment,
                    order=order,
                    prompt=f'Which action best verifies requirement {order}?',
                    options=[
                        f'Check requirement {order} in a test.',
                        f'Ignore requirement {order}.',
                        f'Disable the validation for {order}.',
                        f'Retry requirement {order} without evidence.',
                    ],
                    correct_answer=f'Check requirement {order} in a test.',
                    rationale='A focused test produces evidence that the requirement is satisfied.',
                )

        stdout = StringIO()
        stderr = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                'audit_apexstratos_inventory',
                stdout=stdout,
                stderr=stderr,
            )

        self.assertIn(
            '1/720 complete published assessments and 10/7200 complete questions (1 duplicate assessment(s) excluded)',
            stdout.getvalue(),
        )


class PublishedAssessmentLibraryIntegrationTests(TestCase):
    eat = ZoneInfo('Africa/Nairobi')

    def _seed_existing_slot_conflicts(self):
        tutorial = Tutorial.objects.create(
            month=1,
            week=1,
            day=0,
            daily_slot=1,
            field='Software Development',
            title='Existing software tutorial',
            description='Existing tutorial record preserved during content import.',
            learning_objectives=['Identify a requirement.', 'Test the requirement.', 'Record evidence.'],
            concept_explanation='A test links a requirement to observed behavior.',
            terminology_and_components='A requirement and a test are related evidence.',
            why_it_matters='Evidence supports reliable decisions.',
            how_it_works='Compare observed behavior with an expected result.',
            worked_examples='Test an accepted and a rejected input.',
            common_mistakes='Do not treat access as proof of capability.',
            practical_application='Write a test for a learner workflow.',
            decisions_and_tradeoffs='Prefer sufficient evidence with minimal data.',
            related_concepts='Requirements, testing, and evidence.',
            scheduled_for=timezone.now(),
            status='published',
            published_at=timezone.now(),
        )
        sponsored = SponsoredViewAssessment.objects.create(
            week=1,
            slot=1,
            field='Software Development',
            title='Existing sponsored assessment',
            description='Existing sponsored record preserved during content import.',
            learning_objectives=['Identify a requirement.', 'Test the requirement.', 'Record evidence.'],
            status='published',
            published_at=timezone.now(),
        )
        contest = AssessmentSchedule.objects.create(
            month=1,
            week=1,
            day=4,
            assessment_slot=1,
            field='Software Development',
            title='Existing main contest assessment',
            description='Existing contest record preserved during content import.',
            learning_objectives=['Identify a requirement.', 'Test the requirement.', 'Record evidence.'],
            scheduled_for=timezone.now(),
            duration_minutes=20,
            status='published',
            published_at=timezone.now(),
        )
        for assessment, model, foreign_key in (
            (tutorial, TutorialQuestion, 'tutorial'),
            (sponsored, SponsoredViewQuestion, 'assessment'),
            (contest, AssessmentScheduleQuestion, 'assessment'),
        ):
            for order in range(1, 11):
                correct = f'Verify the expected result for item {order}.'
                model.objects.create(
                    **{foreign_key: assessment},
                    order=order,
                    prompt=f'Which action verifies existing schedule item {order}?',
                    options=[
                        correct,
                        f'Ignore the expected result for item {order}.',
                        f'Disable its validation for item {order}.',
                        f'Retry item {order} without recording evidence.',
                    ],
                    correct_answer=correct,
                    rationale='A direct check against expected behavior produces evidence.',
                )

    def test_populates_and_starts_real_assessments_without_publishing_sensitive_fields(self):
        self._seed_existing_slot_conflicts()
        dry_run = StringIO()
        call_command(
            'bootstrap_apexstratos_libraries',
            '--allow-partial',
            '--preserve-existing-slots',
            stdout=dry_run,
            stderr=StringIO(),
        )
        self.assertIn('would_insert=1501', dry_run.getvalue())
        self.assertIn('failed=656', dry_run.getvalue())
        self.assertEqual(Tutorial.objects.count(), 1)
        self.assertEqual(SponsoredViewAssessment.objects.count(), 1)
        self.assertEqual(AssessmentSchedule.objects.count(), 1)

        output = StringIO()
        call_command(
            'bootstrap_apexstratos_libraries',
            '--apply',
            '--publish',
            '--allow-partial',
            '--preserve-existing-slots',
            stdout=output,
            stderr=StringIO(),
        )

        self.assertEqual(Tutorial.objects.count(), 512)
        self.assertEqual(TutorialQuestion.objects.count(), 5_120)
        self.assertEqual(Tutorial.objects.filter(status='published').count(), 384)
        self.assertEqual(SponsoredViewAssessment.objects.count(), 560)
        self.assertEqual(SponsoredViewQuestion.objects.count(), 5_600)
        self.assertEqual(SponsoredViewAssessment.objects.filter(status='published').count(), 400)
        self.assertEqual(AssessmentSchedule.objects.count(), 432)
        self.assertEqual(AssessmentScheduleQuestion.objects.count(), 4_320)
        self.assertEqual(AssessmentSchedule.objects.filter(status='published').count(), 288)
        self.assertIn('skipped_schedule_conflict=3', output.getvalue())
        self.assertIn('failed=656', output.getvalue())
        for model in (Tutorial, SponsoredViewAssessment, AssessmentSchedule):
            self.assertEqual(
                model.objects.filter(
                    field__in=('Medical and Health', 'Law and Society'),
                    status='published',
                ).count(),
                0,
            )

        student = User.objects.create_user(
            email='assessment-library-learner@example.test',
            username='assessment-library-learner',
            password='test-password',
            phone_number='0712345678',
        )
        client = APIClient()
        client.force_authenticate(student)

        tutorial_catalog = client.get(
            reverse('tutorial-list'),
            {'field': 'Software Development', 'week': 8},
        )
        self.assertEqual(tutorial_catalog.status_code, 200)
        self.assertEqual(tutorial_catalog.data['count'], 8)
        tutorial = Tutorial.objects.filter(
            field='Software Development',
            month=2,
            week=4,
            status='published',
        ).order_by('day', 'daily_slot').first()
        self.assertIsNotNone(tutorial)
        self.assertEqual(len(tutorial_catalog.data['results'][0]['questions']), 10)
        self.assertNotIn('correct_answer', tutorial_catalog.data['results'][0]['questions'][0])

        tutorial_pages = client.get(
            reverse('tutorial-list'),
            {'field': 'Software Development', 'page_size': 20},
        )
        self.assertEqual(tutorial_pages.status_code, 200)
        self.assertEqual(tutorial_pages.data['count'], 64)
        self.assertEqual(len(tutorial_pages.data['results']), 20)
        self.assertIsNotNone(tutorial_pages.data['next'])
        tutorial_search = client.get(
            reverse('tutorial-list'),
            {'field': 'Software Development', 'topic': 'Existing tutorial record'},
        )
        self.assertEqual(tutorial_search.status_code, 200)
        self.assertGreaterEqual(tutorial_search.data['count'], 1)
        self.assertTrue(
            all(
                'existing tutorial record' in f"{item['title']} {item['description']}".lower()
                for item in tutorial_search.data['results']
            )
        )

        monday = datetime(2026, 10, 12, 10, tzinfo=self.eat)
        with patch('apps.cohorts.views.timezone.now', return_value=monday):
            tutorial_start = client.post(
                reverse('tutorial-attempt-start', kwargs={'tutorial_id': tutorial.id}),
                {},
                format='json',
            )
        self.assertEqual(tutorial_start.status_code, 201)
        self.assertEqual(len(tutorial_start.data['questions']), 10)
        self.assertNotIn('correct_answer', tutorial_start.data['questions'][0])
        tutorial_attempt = TutorialAttempt.objects.get(id=tutorial_start.data['id'])
        tutorial_answers = {
            str(question.id): question.correct_answer
            for question in tutorial.questions.order_by('order')
        }
        tutorial_reasoning = {
            str(question.id): 'This explains the evidence-based choice.'
            for question in tutorial.questions.filter(requires_reasoning=True)
        }
        with patch('apps.cohorts.views.timezone.now', return_value=monday):
            tutorial_submission = client.post(
                reverse(
                    'tutorial-attempt-submit',
                    kwargs={'attempt_id': tutorial_attempt.id},
                ),
                {'answers': tutorial_answers, 'reasoning': tutorial_reasoning},
                format='json',
            )
        self.assertEqual(tutorial_submission.status_code, 200)
        self.assertEqual(tutorial_submission.data['score'], 100)
        tutorial_progress = TutorialProgress.objects.get(user=student, tutorial=tutorial)
        self.assertEqual(tutorial_progress.best_score, 100)
        self.assertEqual(tutorial_progress.attempt_count, 1)

        sponsored = SponsoredViewAssessment.objects.get(
            field='Education',
            week=8,
            slot=1,
            status='published',
        )
        unpaid_sponsored_catalog = client.get(
            reverse('sponsored-view-assessment-list'),
            {'field': sponsored.field, 'week': sponsored.week},
        )
        unpaid_sponsored = next(
            item
            for item in unpaid_sponsored_catalog.data['results']
            if item['id'] == str(sponsored.id)
        )
        self.assertFalse(unpaid_sponsored['has_verified_access'])
        self.assertFalse(unpaid_sponsored['can_start'])
        self.assertEqual(unpaid_sponsored['access_price_kes'], 20)
        SponsoredViewPayment.objects.create(
            user=student,
            assessment=sponsored,
            amount_kes=20,
            payment_reference='CONTENT-TEST-SPONSORED-01',
            status='verified',
            requested_at=monday,
            verified_at=monday,
        )
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday):
            sponsored_start = client.post(
                reverse(
                    'sponsored-view-attempt-start',
                    kwargs={
                        'payment_id': SponsoredViewPayment.objects.get(
                            user=student,
                            assessment=sponsored,
                        ).id,
                    },
                ),
                {},
                format='json',
            )
        self.assertEqual(sponsored_start.status_code, 201)
        self.assertEqual(len(sponsored_start.data['questions']), 10)
        self.assertNotIn('correct_answer', sponsored_start.data['questions'][0])
        sponsored_catalog = client.get(
            reverse('sponsored-view-assessment-list'),
            {
                'field': sponsored.field,
                'week': sponsored.week,
                'topic': sponsored.title.split()[-1],
            },
        )
        self.assertEqual(sponsored_catalog.status_code, 200)
        self.assertIn(
            str(sponsored.id),
            {str(item['id']) for item in sponsored_catalog.data['results']},
        )
        self.assertTrue(
            all(item['has_verified_access'] for item in sponsored_catalog.data['results'])
        )
        sponsored_attempt = SponsoredViewAttempt.objects.get(
            id=sponsored_start.data['id']
        )
        sponsored_answers = {
            str(question.id): question.correct_answer
            for question in sponsored.questions.order_by('order')
        }
        sponsored_reasoning = {
            str(question.id): 'This explains the evidence-based choice.'
            for question in sponsored.questions.filter(requires_reasoning=True)
        }
        with patch('apps.cohorts.sponsored_views.timezone.now', return_value=monday):
            sponsored_submission = client.post(
                reverse(
                    'sponsored-view-attempt-submit',
                    kwargs={'attempt_id': sponsored_attempt.id},
                ),
                {'answers': sponsored_answers, 'reasoning': sponsored_reasoning},
                format='json',
            )
        self.assertEqual(sponsored_submission.status_code, 200)
        self.assertEqual(sponsored_submission.data['score'], 100)

        contest = AssessmentSchedule.objects.get(
            field='Education',
            month=2,
            week=4,
            day=4,
            assessment_slot=1,
            status='published',
        )
        unpaid_contest_catalog = client.get(
            reverse('contest-assessment-library'),
            {
                'field': contest.field,
                'week': (contest.month - 1) * 4 + contest.week,
            },
        )
        unpaid_contest = next(
            item
            for item in unpaid_contest_catalog.data['results']
            if item['id'] == str(contest.id)
        )
        self.assertFalse(unpaid_contest['has_verified_access'])
        self.assertFalse(unpaid_contest['can_start'])
        self.assertEqual(unpaid_contest['access_price_kes'], 100)
        friday = datetime(2026, 10, 16, 10, tzinfo=self.eat)
        ParticipationPayment.objects.create(
            user=student,
            full_name='Assessment Library Learner',
            phone_number='0712345678',
            field='Education',
            amount_kes=100,
            till_number='1598106',
            payment_reference='CONTENT-TEST-MAIN-01',
            mpesa_transaction_id='CONTENT-TEST-TXN-01',
            status='verified',
            verification_notes='Verified test fixture for a published assessment start.',
            verified_at=friday,
            expires_at=friday + timedelta(days=3),
        )
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            contest_start = client.post(
                reverse('contest-assessment-start', kwargs={'assessment_id': contest.id}),
                {},
                format='json',
            )
        self.assertEqual(contest_start.status_code, 201)
        self.assertEqual(len(contest_start.data['questions']), 10)
        self.assertNotIn('correct_answer', contest_start.data['questions'][0])
        contest_catalog = client.get(
            reverse('contest-assessment-library'),
            {
                'field': contest.field,
                'week': (contest.month - 1) * 4 + contest.week,
                'topic': contest.title.split()[-1],
            },
        )
        self.assertEqual(contest_catalog.status_code, 200)
        self.assertIn(
            str(contest.id),
            {str(item['id']) for item in contest_catalog.data['results']},
        )
        self.assertTrue(
            all(item['has_verified_access'] for item in contest_catalog.data['results'])
        )
        contest_answers = {
            str(question.id): question.correct_answer
            for question in contest.questions.order_by('order')
        }
        contest_reasoning = {
            str(question.id): 'This explains the evidence-based choice.'
            for question in contest.questions.filter(requires_reasoning=True)
        }
        with patch('apps.cohorts.programme_views.timezone.now', return_value=friday):
            contest_submission = client.post(
                reverse(
                    'contest-assessment-submit',
                    kwargs={'attempt_id': contest_start.data['id']},
                ),
                {'answers': contest_answers, 'reasoning': contest_reasoning},
                format='json',
            )
        self.assertEqual(contest_submission.status_code, 200)
        self.assertEqual(contest_submission.data['score'], 100)

        unchanged_output = StringIO()
        call_command(
            'bootstrap_apexstratos_libraries',
            '--apply',
            '--allow-partial',
            '--preserve-existing-slots',
            stdout=unchanged_output,
            stderr=StringIO(),
        )
        self.assertIn('inserted=0', unchanged_output.getvalue())
        self.assertIn('skipped_existing=1501', unchanged_output.getvalue())
