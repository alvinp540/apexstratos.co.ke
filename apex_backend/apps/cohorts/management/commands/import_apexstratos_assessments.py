import json
import re
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cohorts.models import (
    AssessmentSchedule,
    AssessmentScheduleQuestion,
    SponsoredViewAssessment,
    SponsoredViewQuestion,
    Tutorial,
    TutorialQuestion,
)
from apps.cohorts.tutorial_schedule import CAPABILITY_FIELDS


NAMESPACE = uuid.UUID('ac0b702e-b758-4c29-a101-268ba66ad8db')
EXTERNAL_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$')
TUTORIAL_TEXT_FIELDS = (
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
DIFFICULTIES = {'foundation', 'developing', 'integrated'}
PLACEHOLDER = re.compile(
    r'\b(?:lorem ipsum|placeholder|coming soon|tbd|todo|sample question|question text here)\b',
    re.IGNORECASE,
)


def _required_text(value, path, errors):
    if not isinstance(value, str) or not value.strip() or PLACEHOLDER.search(value):
        errors.append(f'{path}: expected non-placeholder text.')
        return ''
    return value.strip()


def _validate_pack(payload, library):
    errors = []
    if not isinstance(payload, dict) or payload.get('schema_version') != 1:
        raise CommandError('Content pack must be a JSON object with schema_version: 1.')
    provenance = payload.get('provenance')
    if not isinstance(provenance, dict):
        raise CommandError('Content pack must include provenance metadata.')
    for key in ('title', 'author', 'license', 'attribution', 'reference'):
        if not isinstance(provenance.get(key), str) or not provenance[key].strip():
            errors.append(f'provenance.{key}: required non-empty text.')
    assessments = payload.get('assessments')
    if not isinstance(assessments, list) or not assessments:
        raise CommandError('Content pack assessments must be a non-empty list.')

    seen_ids = set()
    seen_slots = set()
    seen_assessment_fingerprints = set()
    seen_question_prompts = {}
    for index, item in enumerate(assessments):
        location = f'assessments[{index}]'
        if not isinstance(item, dict):
            errors.append(f'{location}: expected an object.')
            continue
        external_id = item.get('external_id')
        if not isinstance(external_id, str) or not EXTERNAL_ID.fullmatch(external_id):
            errors.append(f'{location}.external_id: use 1–120 letters, digits, dots, colons, underscores, or hyphens.')
        elif external_id in seen_ids:
            errors.append(f'{location}.external_id: duplicate {external_id!r} in content pack.')
        else:
            seen_ids.add(external_id)
        field = item.get('field')
        if field not in CAPABILITY_FIELDS:
            errors.append(f'{location}.field: must match one of the ten official study areas.')
        week = item.get('week')
        if not isinstance(week, int) or isinstance(week, bool) or not 1 <= week <= 8:
            errors.append(f'{location}.week: must be an integer from 1 through 8.')
        day = item.get('day')
        allowed_days = range(4) if library in {'tutorials', 'sponsored-view'} else range(4, 7)
        if library != 'sponsored-view' and (
            not isinstance(day, int) or isinstance(day, bool) or day not in allowed_days
        ):
            expected = '0–3 (Monday–Thursday)' if library == 'tutorials' else '4–6 (Friday–Sunday)'
            errors.append(f'{location}.day: must be {expected}.')
        if library == 'sponsored-view' and day is not None:
            errors.append(f'{location}.day: Sponsored View assessments are not assigned individual start days.')
        slot = item.get('slot')
        max_slot = 2 if library == 'tutorials' else 10 if library == 'sponsored-view' else 3
        if not isinstance(slot, int) or isinstance(slot, bool) or not 1 <= slot <= max_slot:
            errors.append(f'{location}.slot: must be an integer from 1 through {max_slot}.')
        if (
            isinstance(field, str)
            and isinstance(week, int)
            and not isinstance(week, bool)
            and isinstance(slot, int)
            and not isinstance(slot, bool)
            and (library == 'sponsored-view' or isinstance(day, int) and not isinstance(day, bool))
        ):
            schedule_key = (field, week, slot) if library == 'sponsored-view' else (field, week, day, slot)
            if schedule_key in seen_slots:
                errors.append(f'{location}: duplicate schedule slot {schedule_key!r}.')
            seen_slots.add(schedule_key)

        for key in ('title', 'description'):
            _required_text(item.get(key), f'{location}.{key}', errors)
        if item.get('difficulty', 'foundation') not in DIFFICULTIES:
            errors.append(f'{location}.difficulty: unsupported difficulty.')
        if item.get('expert_reviewed') is True:
            errors.append(
                f'{location}.expert_reviewed: only an administrator can record human expert review.'
            )
        objectives = item.get('learning_objectives')
        if (
            not isinstance(objectives, list)
            or len(objectives) < 3
            or any(not isinstance(text, str) or not text.strip() or PLACEHOLDER.search(text) for text in objectives)
        ):
            errors.append(f'{location}.learning_objectives: provide at least three substantive objectives.')
        if library == 'tutorials':
            for key in TUTORIAL_TEXT_FIELDS:
                _required_text(item.get(key), f'{location}.{key}', errors)
            duration = item.get('duration_minutes')
            if duration is not None and (
                not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 240
            ):
                errors.append(f'{location}.duration_minutes: use an integer from 1 through 240 or omit it.')
        elif item.get('duration_minutes', 20) != 20:
            errors.append(f'{location}.duration_minutes: timed programme assessments must last 20 minutes.')
        passing_score = item.get('passing_score', 70)
        if (
            library == 'main-contest'
            and (
                not isinstance(passing_score, (int, float))
                or isinstance(passing_score, bool)
                or not 0 <= passing_score <= 100
            )
        ):
            errors.append(f'{location}.passing_score: use a number from 0 to 100.')
        questions = item.get('questions')
        if not isinstance(questions, list) or len(questions) != 10:
            errors.append(f'{location}.questions: exactly ten questions are required.')
            continue
        prompts = set()
        fingerprint_questions = []
        for question_index, question in enumerate(questions):
            question_location = f'{location}.questions[{question_index}]'
            if not isinstance(question, dict):
                errors.append(f'{question_location}: expected an object.')
                continue
            order = question.get('order')
            if not isinstance(order, int) or isinstance(order, bool) or order != question_index + 1:
                errors.append(f'{question_location}.order: questions must be ordered 1 through 10.')
            prompt = _required_text(question.get('prompt'), f'{question_location}.prompt', errors)
            normalized_prompt = ' '.join(prompt.casefold().split())
            if normalized_prompt and normalized_prompt in prompts:
                errors.append(f'{question_location}.prompt: duplicated within this assessment.')
            prompts.add(normalized_prompt)
            if normalized_prompt in seen_question_prompts:
                previous_location = seen_question_prompts[normalized_prompt]
                errors.append(
                    f'{question_location}.prompt: duplicates a question in {previous_location}.'
                )
            elif normalized_prompt:
                seen_question_prompts[normalized_prompt] = question_location
            options = question.get('options')
            if (
                not isinstance(options, list)
                or len(options) != 4
                or any(
                    not isinstance(option, str)
                    or not option.strip()
                    or PLACEHOLDER.search(option)
                    for option in options
                )
                or len({option.casefold().strip() for option in options if isinstance(option, str)}) != 4
            ):
                errors.append(f'{question_location}.options: provide exactly four distinct, non-placeholder options.')
            answer = question.get('correct_answer')
            if not isinstance(answer, str) or not isinstance(options, list) or answer not in options:
                errors.append(f'{question_location}.correct_answer: must exactly match one of the four options.')
            _required_text(question.get('rationale'), f'{question_location}.rationale', errors)
            if 'requires_reasoning' in question and not isinstance(question['requires_reasoning'], bool):
                errors.append(f'{question_location}.requires_reasoning: expected true or false.')
            if (
                normalized_prompt
                and isinstance(options, list)
                and all(isinstance(option, str) and option.strip() for option in options)
                and isinstance(answer, str)
            ):
                fingerprint_questions.append({
                    'prompt': normalized_prompt,
                    'options': sorted(' '.join(option.casefold().split()) for option in options),
                    'answer': ' '.join(answer.casefold().split()),
                })
        if len(fingerprint_questions) == 10:
            fingerprint = json.dumps(
                sorted(fingerprint_questions, key=lambda question: question['prompt']),
                ensure_ascii=True,
                sort_keys=True,
                separators=(',', ':'),
            )
            if fingerprint in seen_assessment_fingerprints:
                errors.append(f'{location}.questions: duplicates a complete assessment question set in this pack.')
            seen_assessment_fingerprints.add(fingerprint)

    if errors:
        raise CommandError('Invalid content pack:\n- ' + '\n- '.join(errors[:100]))
    return assessments


class Command(BaseCommand):
    help = 'Validate and append a provenance-tracked question-library JSON content pack.'

    def add_arguments(self, parser):
        parser.add_argument('--library', required=True, choices=('tutorials', 'sponsored-view', 'main-contest'))
        parser.add_argument('--file', required=True, type=Path)
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Create validated assessments as drafts. Omit this flag to perform a dry run.',
        )

    def handle(self, *args, **options):
        path = options['file']
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except OSError as error:
            raise CommandError(f'Cannot read content pack {path}: {error}') from error
        except json.JSONDecodeError as error:
            raise CommandError(f'Content pack is not valid JSON: {error}') from error

        library = options['library']
        try:
            assessments = _validate_pack(payload, library)
        except CommandError as error:
            raise CommandError(f'Content pack {path} failed validation: {error}') from error
        models = {
            'tutorials': (Tutorial, TutorialQuestion),
            'sponsored-view': (SponsoredViewAssessment, SponsoredViewQuestion),
            'main-contest': (AssessmentSchedule, AssessmentScheduleQuestion),
        }
        model, question_model = models[library]
        namespace = uuid.uuid5(NAMESPACE, library)
        create_count = 0
        unchanged_count = 0

        for item in assessments:
            stable_id = uuid.uuid5(namespace, item['external_id'])
            existing = model.objects.filter(id=stable_id).first()
            if existing:
                expected_source = (
                    f'{payload["provenance"]["title"]} — {payload["provenance"]["reference"]}'
                )
                expected_attribution = (
                    f'{payload["provenance"]["author"]}; {payload["provenance"]["attribution"]}'
                )
                expected_week = item['week']
                expected_month, expected_local_week = divmod(expected_week - 1, 4)
                if library == 'sponsored-view':
                    schedule_matches = (
                        existing.week == expected_week
                        and existing.slot == item['slot']
                    )
                    content_matches = (
                        existing.duration_minutes == 20
                        and existing.difficulty == item.get('difficulty', 'foundation')
                    )
                else:
                    schedule_matches = (
                        existing.month == expected_month + 1
                        and existing.week == expected_local_week + 1
                        and existing.day == item['day']
                        and (
                            existing.daily_slot == item['slot']
                            if library == 'tutorials'
                            else existing.assessment_slot == item['slot']
                        )
                    )
                    content_matches = (
                        existing.duration_minutes == (
                            item.get('duration_minutes')
                            if library == 'tutorials'
                            else 20
                        )
                        and existing.difficulty == item.get('difficulty', 'foundation')
                    )
                    if library == 'main-contest':
                        content_matches = content_matches and (
                            existing.passing_score == item.get('passing_score', 70)
                        )
                if (
                    existing.imported_external_id != item['external_id']
                    or existing.content_source != expected_source
                    or existing.content_license != payload['provenance']['license']
                    or existing.content_attribution != expected_attribution
                    or existing.field != item['field']
                    or existing.title != item['title'].strip()
                    or existing.description != item['description'].strip()
                    or existing.learning_objectives != item['learning_objectives']
                    or not schedule_matches
                    or not content_matches
                    or existing.expert_reviewed != item.get('expert_reviewed', False)
                    or list(existing.questions.order_by('order').values_list(
                        'order', 'prompt', 'options', 'correct_answer', 'rationale',
                    )) != [
                        (
                            question['order'],
                            question['prompt'].strip(),
                            question['options'],
                            question['correct_answer'],
                            question['rationale'].strip(),
                        )
                        for question in item['questions']
                    ]
                ):
                    raise CommandError(
                        f'Existing imported assessment {item["external_id"]!r} differs from this pack. '
                        'It was not overwritten; create a new external_id for a new content version.'
                    )
                unchanged_count += 1
                continue
            week = item['week']
            month, local_week = divmod(week - 1, 4)
            schedule = {
                'id': stable_id,
                'field': item['field'],
                'title': item['title'].strip(),
                'description': item['description'].strip(),
                'imported_external_id': item['external_id'],
                'content_source': (
                    f'{payload["provenance"]["title"]} — {payload["provenance"]["reference"]}'
                ),
                'content_license': payload['provenance']['license'].strip(),
                'content_attribution': (
                    f'{payload["provenance"]["author"]}; {payload["provenance"]["attribution"]}'
                ),
                'learning_objectives': item['learning_objectives'],
                'difficulty': item.get('difficulty', 'foundation'),
                'status': 'draft',
                'expert_reviewed': item.get('expert_reviewed', False),
            }
            if library == 'tutorials':
                schedule.update({
                    'month': month + 1,
                    'week': local_week + 1,
                    'day': item['day'],
                    'daily_slot': item['slot'],
                    'scheduled_for': timezone.now(),
                    **{key: item[key].strip() for key in TUTORIAL_TEXT_FIELDS},
                    'duration_minutes': item.get('duration_minutes'),
                })
            elif library == 'main-contest':
                schedule.update({
                    'month': month + 1,
                    'week': local_week + 1,
                    'day': item['day'],
                    'assessment_slot': item['slot'],
                    'scheduled_for': timezone.now(),
                    'duration_minutes': 20,
                    'passing_score': item.get('passing_score', 70),
                })
            else:
                schedule.update({
                    'week': week,
                    'slot': item['slot'],
                    'duration_minutes': item.get('duration_minutes', 20),
                })
            if options['apply']:
                try:
                    with transaction.atomic():
                        assessment = model.objects.create(**schedule)
                        question_kwargs = (
                            {'tutorial': assessment}
                            if library == 'tutorials'
                            else {'assessment': assessment}
                        )
                        question_model.objects.bulk_create([
                            question_model(
                                id=uuid.uuid5(stable_id, f'question:{question["order"]}'),
                                order=question['order'],
                                prompt=question['prompt'].strip(),
                                options=question['options'],
                                correct_answer=question['correct_answer'],
                                rationale=question['rationale'].strip(),
                                requires_reasoning=question.get('requires_reasoning', False),
                                **(
                                    {'question_type': 'multiple_choice'}
                                    if library != 'sponsored-view'
                                    else {}
                                ),
                                **question_kwargs,
                            )
                            for question in item['questions']
                        ])
                except IntegrityError as error:
                    raise CommandError(
                        f'Cannot add {item["external_id"]!r} without overwriting existing content: {error}'
                    ) from error
            create_count += 1

        action = 'Created' if options['apply'] else 'Would create'
        self.stdout.write(
            f'{action} {create_count} {library} assessment(s) as drafts; '
            f'{unchanged_count} unchanged idempotent assessment(s) skipped. '
            f'Validated source provenance: {payload["provenance"]["title"]} '
            f'({payload["provenance"]["license"]}).'
        )
        if not options['apply']:
            self.stdout.write('No database records were changed. Re-run with --apply to append the validated draft content.')
