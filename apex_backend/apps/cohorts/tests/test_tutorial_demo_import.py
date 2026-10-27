from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.cohorts.models import AssessmentSchedule, SponsoredViewAssessment, Tutorial


class TutorialDemoImportTests(TestCase):
    def test_import_adds_only_requested_tutorials_as_drafts(self):
        output = StringIO()

        call_command(
            'import_tutorial_demo',
            '--limit',
            '1',
            '--apply',
            stdout=output,
        )

        tutorial = Tutorial.objects.get()
        self.assertEqual(tutorial.status, 'draft')
        self.assertEqual(tutorial.questions.count(), 10)
        self.assertEqual(AssessmentSchedule.objects.count(), 0)
        self.assertEqual(SponsoredViewAssessment.objects.count(), 0)
        self.assertIn('Importing 1 validated tutorials as drafts', output.getvalue())

    def test_dry_run_does_not_change_any_assessment_library(self):
        output = StringIO()

        call_command(
            'import_tutorial_demo',
            '--limit',
            '1',
            stdout=output,
        )

        self.assertEqual(Tutorial.objects.count(), 0)
        self.assertEqual(AssessmentSchedule.objects.count(), 0)
        self.assertEqual(SponsoredViewAssessment.objects.count(), 0)
        self.assertIn('Dry run only', output.getvalue())

