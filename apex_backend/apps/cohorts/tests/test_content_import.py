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
    SponsoredViewPayment,
    SponsoredViewQuestion,
    Tutorial,
    TutorialQuestion,
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

    def test_seeds_real_starter_assessments_idempotently_without_sensitive_fields(self):
        seed = 'seed_apexstratos_starter_libraries'
        call_command(seed, '--apply', stdout=StringIO())
        call_command(seed, '--apply', stdout=StringIO())

        expected = (
            (Tutorial, TutorialQuestion, 'tutorial'),
            (SponsoredViewAssessment, SponsoredViewQuestion, 'assessment'),
            (AssessmentSchedule, AssessmentScheduleQuestion, 'assessment'),
        )
        for assessment_model, question_model, relation in expected:
            assessment = assessment_model.objects.get(status='published')
            self.assertEqual(question_model.objects.filter(**{relation: assessment}).count(), 10)
            self.assertIn('apex-starter-', assessment.imported_external_id)
            self.assertFalse(
                assessment_model.objects.filter(
                    field__in=('Medical and Health', 'Law and Society'),
                    status='published',
                ).exists()
            )

        self.assertEqual(Tutorial.objects.count(), 1)
        self.assertEqual(SponsoredViewAssessment.objects.count(), 1)
        self.assertEqual(AssessmentSchedule.objects.count(), 1)
