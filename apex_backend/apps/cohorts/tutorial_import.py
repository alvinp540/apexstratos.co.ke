import json
import zipfile
from itertools import product

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .models import Tutorial, TutorialQuestion
from .tutorial_schedule import CAPABILITY_FIELDS, TUTORIALS_PER_DAY

MAX_BUNDLE_BYTES = 1500 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024
MIN_TEACHING_SECTION_CHARS = 80
TEACHING_SECTIONS = (
    'concept_explanation',
    'terminology_and_components',
    'why_it_matters',
    'how_it_works',
    'worked_examples',
    'common_mistakes',
    'practical_application',
    'decisions_and_tradeoffs',
    'related_concepts',
)
_REQUIRED_TUTORIAL_FIELDS = {
    'field', 'daily_slot', 'title', 'description', 'learning_objectives',
    'difficulty', 'duration_minutes', 'video_path', 'questions',
    *TEACHING_SECTIONS,
}
_REQUIRED_QUESTION_FIELDS = {'order', 'question_type', 'prompt', 'options', 'correct_answer', 'rationale'}


def _validate_video_path(path):
    if not isinstance(path, str) or not path.startswith('videos/'):
        raise ValidationError('Every video_path must point inside the archive videos/ directory.')
    if '..' in path.split('/') or '\\' in path or not path.lower().endswith('.mp4'):
        raise ValidationError('Video files must be safe internal .mp4 archive paths.')
    return path


def _validate_manifest(manifest, archive):
    if not isinstance(manifest, dict) or not isinstance(manifest.get('tutorials'), list):
        raise ValidationError('manifest.json must contain a tutorials list.')

    lessons = manifest['tutorials']
    expected_slots = set(product(CAPABILITY_FIELDS, range(1, TUTORIALS_PER_DAY + 1)))
    actual_slots = set()
    video_paths = set()
    errors = []
    names = archive.namelist()
    available_files = set(names)
    if len(names) != len(available_files):
        errors.append('The ZIP archive must not contain duplicate member names.')

    if len(lessons) != len(expected_slots):
        errors.append(f'The daily package must contain exactly {len(expected_slots)} tutorials.')

    for lesson_number, lesson in enumerate(lessons, start=1):
        if not isinstance(lesson, dict):
            errors.append(f'Tutorial {lesson_number} must be an object.')
            continue
        missing = _REQUIRED_TUTORIAL_FIELDS - lesson.keys()
        if missing:
            errors.append(f'Tutorial {lesson_number} is missing: {", ".join(sorted(missing))}.')
            continue
        field_name = lesson['field']
        slot = lesson['daily_slot']
        if field_name not in CAPABILITY_FIELDS or slot not in (1, 2):
            errors.append(f'Tutorial {lesson_number} has an unknown capability field or daily slot.')
            continue
        key = (field_name, slot)
        if key in actual_slots:
            errors.append(f'Duplicate tutorial schedule slot for {field_name}, tutorial {slot}.')
        actual_slots.add(key)

        video_path = _validate_video_path(lesson['video_path'])
        video_paths.add(video_path)
        if video_path not in available_files:
            errors.append(f'Missing internal video file: {video_path}.')
        else:
            info = archive.getinfo(video_path)
            if info.file_size > MAX_VIDEO_BYTES:
                errors.append(f'Video exceeds {MAX_VIDEO_BYTES // (1024 * 1024)} MB: {video_path}.')
            elif info.file_size < 12 or archive.read(video_path)[4:8] != b'ftyp':
                errors.append(f'File is not a recognized MP4 video: {video_path}.')

        if lesson['difficulty'] not in dict(Tutorial.DIFFICULTY_CHOICES):
            errors.append(f'Tutorial {lesson_number} has an unsupported difficulty.')
        if not isinstance(lesson['title'], str) or len(lesson['title'].strip()) < 8:
            errors.append(f'Tutorial {lesson_number} needs a descriptive title.')
        if not isinstance(lesson['description'], str) or len(lesson['description'].strip()) < 30:
            errors.append(f'Tutorial {lesson_number} needs a meaningful description.')
        if not isinstance(lesson['learning_objectives'], list) or len(lesson['learning_objectives']) < 3:
            errors.append(f'Tutorial {lesson_number} needs at least three learning objectives.')
        for section in TEACHING_SECTIONS:
            if not isinstance(lesson[section], str) or len(lesson[section].strip()) < MIN_TEACHING_SECTION_CHARS:
                errors.append(f'Tutorial {lesson_number} needs developed {section} teaching content (at least {MIN_TEACHING_SECTION_CHARS} characters).')
        if not isinstance(lesson['duration_minutes'], int) or isinstance(lesson['duration_minutes'], bool) or lesson['duration_minutes'] < 1:
            errors.append(f'Tutorial {lesson_number} needs a positive, realistic duration.')
        if not isinstance(lesson['questions'], list) or len(lesson['questions']) != 5:
            errors.append(f'Tutorial {lesson_number} must contain exactly five questions.')
        else:
            for expected_order, question in enumerate(lesson['questions'], start=1):
                if not isinstance(question, dict) or _REQUIRED_QUESTION_FIELDS - question.keys():
                    errors.append(f'Tutorial {lesson_number}, question {expected_order} is incomplete.')
                    continue
                if question['order'] != expected_order:
                    errors.append(f'Tutorial {lesson_number} questions must be numbered 1 through 5.')
                if not isinstance(question['prompt'], str) or len(question['prompt'].strip()) < 30:
                    errors.append(f'Tutorial {lesson_number}, question {expected_order} needs a practical scenario prompt.')
                if question['question_type'] not in dict(TutorialQuestion.QUESTION_TYPE_CHOICES):
                    errors.append(f'Tutorial {lesson_number}, question {expected_order} has an invalid type.')
                if question['question_type'] == 'multiple_choice':
                    options = question['options']
                    if not isinstance(options, list) or len(options) < 2 or question['correct_answer'] not in options:
                        errors.append(f'Tutorial {lesson_number}, question {expected_order} needs valid options and a matching answer.')

    if actual_slots != expected_slots:
        errors.append('The package must include both tutorial slots for all ten capability fields.')
    if len(video_paths) != len(expected_slots):
        errors.append('Each tutorial needs its own video file in the package.')
    if available_files != {'manifest.json'} | video_paths:
        errors.append('The ZIP archive may contain only manifest.json and the referenced internal tutorial videos.')
    if errors:
        raise ValidationError(errors)
    return lessons


@transaction.atomic
def import_daily_tutorial_bundle(*, uploaded_bundle, month, week, day, scheduled_for, created_by):
    if uploaded_bundle.size > MAX_BUNDLE_BYTES:
        raise ValidationError(f'The bundle may not exceed {MAX_BUNDLE_BYTES // (1024 * 1024)} MB.')
    if month < 1 or week not in range(1, 5) or day not in range(0, 4):
        raise ValidationError('Month, week, and weekday are outside the supported schedule.')
    if timezone.is_naive(scheduled_for):
        scheduled_for = timezone.make_aware(scheduled_for, timezone.get_current_timezone())

    try:
        archive = zipfile.ZipFile(uploaded_bundle)
    except (zipfile.BadZipFile, OSError) as error:
        raise ValidationError('Upload a valid ZIP tutorial bundle.') from error

    with archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_BUNDLE_BYTES:
            raise ValidationError('The uncompressed tutorial bundle is too large.')
        if 'manifest.json' not in archive.namelist():
            raise ValidationError('The ZIP bundle must include manifest.json.')
        try:
            manifest = json.loads(archive.read('manifest.json'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError('manifest.json must contain valid UTF-8 JSON.') from error
        lessons = _validate_manifest(manifest, archive)

        schedule_keys = [(month, week, day, lesson['daily_slot'], lesson['field']) for lesson in lessons]
        if Tutorial.objects.filter(
            month=month,
            week=week,
            day=day,
        ).exists():
            existing_keys = set(Tutorial.objects.filter(month=month, week=week, day=day).values_list('month', 'week', 'day', 'daily_slot', 'field'))
            collisions = [key for key in schedule_keys if key in existing_keys]
            if collisions:
                raise ValidationError('This day already has tutorial records. Archive or edit the existing schedule before re-uploading.')

        created_tutorials = []
        saved_video_names = []
        try:
            for lesson in lessons:
                tutorial = Tutorial(
                    month=month,
                    week=week,
                    day=day,
                    daily_slot=lesson['daily_slot'],
                    field=lesson['field'],
                    title=lesson['title'],
                    description=lesson['description'],
                    learning_objectives=lesson['learning_objectives'],
                    difficulty=lesson['difficulty'],
                    duration_minutes=lesson['duration_minutes'],
                    scheduled_for=scheduled_for,
                    status='draft',
                    created_by=created_by,
                    **{section: lesson[section] for section in TEACHING_SECTIONS},
                )
                video_name = lesson['video_path'].split('/')[-1]
                tutorial.video.save(video_name, ContentFile(archive.read(lesson['video_path'])), save=False)
                saved_video_names.append((tutorial.video.storage, tutorial.video.name))
                tutorial.save()
                created_tutorials.append(tutorial)
                for question in lesson['questions']:
                    TutorialQuestion.objects.create(
                        tutorial=tutorial,
                        order=question['order'],
                        question_type=question['question_type'],
                        prompt=question['prompt'],
                        options=question['options'],
                        correct_answer=question['correct_answer'],
                        rationale=question['rationale'],
                    )
        except Exception:
            for storage, name in saved_video_names:
                if storage.exists(name):
                    storage.delete(name)
            raise

    return created_tutorials
