import json
import tempfile
import zipfile
from io import BytesIO
from itertools import product
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from apps.accounts.models import User
from apps.cohorts.models import Tutorial, TutorialQuestion
from apps.cohorts.tutorial_import import import_daily_tutorial_bundle
from apps.cohorts.tutorial_schedule import CAPABILITY_FIELDS


class DailyTutorialImportTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.storage_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage',
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            },
        )
        self.storage_override.enable()
        self.addCleanup(self.storage_override.disable)
        self.user = User.objects.create_user(
            email='daily-admin@example.test',
            username='daily-admin',
            password='temporary-test-only',
            role='admin',
            is_staff=True,
        )

    def make_manifest(self, omit_last=False):
        lessons = []
        for index, (field, slot) in enumerate(product(CAPABILITY_FIELDS, (1, 2))):
            if omit_last and index == 19:
                continue
            lesson = {
                'field': field,
                'daily_slot': slot,
                'title': f'{field} tutorial {slot}: practical concepts',
                'description': f'A practical session explaining {field} concepts through realistic work scenarios and decisions.',
                'learning_objectives': ['Explain a concept', 'Apply it to a situation', 'Reason about a trade-off'],
                'difficulty': 'foundation',
                'duration_minutes': 20,
                'video_path': f'videos/lesson_{index + 1}.mp4',
                'concept_explanation': 'A detailed explanation of the central concept and the practical problem it helps solve, with context for learners.',
                'terminology_and_components': 'The important terms and components are explained, including how each part interacts with the rest of the system.',
                'why_it_matters': 'This capability matters in practice because reliable decisions depend on understanding the actual constraints and consequences.',
                'how_it_works': 'The process is demonstrated step by step, explaining cause and effect rather than asking learners to memorize a rule.',
                'worked_examples': 'A realistic worked example follows the problem from initial observations through decisions to a defensible outcome.',
                'common_mistakes': 'Common mistakes, why they happen, how to recognize them, and how to correct them are explained with examples.',
                'practical_application': 'Learners apply the idea to a realistic task and identify the evidence they need before choosing an action.',
                'decisions_and_tradeoffs': 'The session compares practical options and explains the risks, benefits, and trade-offs behind each decision.',
                'related_concepts': 'Connections to related field concepts show how this idea fits into broader professional practice.',
                'questions': [
                    {
                        'order': order,
                        'question_type': 'multiple_choice',
                        'prompt': f'A realistic {field} work situation presents a concrete constraint. Which next step best applies the tutorial reasoning? Scenario {order}.',
                        'options': ['Inspect evidence and constraints', 'Ignore the context', 'Repeat a previous action'],
                        'correct_answer': 'Inspect evidence and constraints',
                        'rationale': 'The decision should follow the available evidence and the constraints in the scenario.',
                    }
                    for order in range(1, 6)
                ],
            }
            lessons.append(lesson)
        return {'tutorials': lessons}

    def make_bundle(self, *, omit_last=False):
        manifest = self.make_manifest(omit_last=omit_last)
        bundle_buffer = BytesIO()
        with zipfile.ZipFile(bundle_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(manifest))
            for lesson in manifest['tutorials']:
                archive.writestr(lesson['video_path'], b'\x00\x00\x00\x18ftypisom0000')
        return SimpleUploadedFile('tutorials.zip', bundle_buffer.getvalue(), content_type='application/zip')

    def import_bundle(self, bundle):
        return import_daily_tutorial_bundle(
            uploaded_bundle=bundle,
            month=1,
            week=1,
            day=0,
            scheduled_for=timezone.now(),
            created_by=self.user,
        )

    def test_admin_can_open_the_daily_upload_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('admin:cohorts_tutorial_daily_upload'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Validate and upload daily bundle')

    def test_non_admin_cannot_open_the_daily_upload_page(self):
        learner = User.objects.create_user(
            email='daily-learner@example.test',
            username='daily-learner',
            password='temporary-test-only',
            role='professional',
        )
        self.client.force_login(learner)

        response = self.client.get(reverse('admin:cohorts_tutorial_daily_upload'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_daily_upload_imports_exact_twenty_drafts_with_one_hundred_questions(self):
        with override_settings(MEDIA_ROOT=self.media_directory.name):
            tutorials = self.import_bundle(self.make_bundle())

        self.assertEqual(len(tutorials), 20)
        self.assertEqual(Tutorial.objects.count(), 20)
        self.assertEqual(TutorialQuestion.objects.count(), 100)
        self.assertEqual(Tutorial.objects.filter(status='draft').count(), 20)
        self.assertEqual(Tutorial.objects.exclude(video='').count(), 20)

    def test_invalid_incomplete_day_is_rejected_without_partial_records(self):
        with self.assertRaises(ValidationError):
            self.import_bundle(self.make_bundle(omit_last=True))

        self.assertEqual(Tutorial.objects.count(), 0)
        self.assertEqual(TutorialQuestion.objects.count(), 0)

    def test_same_schedule_cannot_be_reuploaded(self):
        with override_settings(MEDIA_ROOT=self.media_directory.name):
            self.import_bundle(self.make_bundle())
            with self.assertRaises(ValidationError):
                self.import_bundle(self.make_bundle())

        self.assertEqual(Tutorial.objects.count(), 20)
        self.assertEqual(TutorialQuestion.objects.count(), 100)
