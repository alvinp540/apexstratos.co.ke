import json
import uuid
from pathlib import Path
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.cohorts.management.commands.import_apexstratos_assessments import _validate_pack
from apps.cohorts.content_validation import (
    contest_is_complete,
    sponsored_view_is_complete,
    tutorial_is_complete,
)
from apps.cohorts.models import AssessmentSchedule, SponsoredViewAssessment, Tutorial
from apps.cohorts.tutorial_schedule import (
    CAPABILITY_FIELDS,
    EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS,
    EXPECTED_INITIAL_SPONSORED_ASSESSMENTS,
    EXPECTED_INITIAL_TUTORIALS,
)


LIBRARY_COUNTS = {
    'tutorials': EXPECTED_INITIAL_TUTORIALS // len(CAPABILITY_FIELDS),
    'sponsored-view': EXPECTED_INITIAL_SPONSORED_ASSESSMENTS // len(CAPABILITY_FIELDS),
    'main-contest': EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS // len(CAPABILITY_FIELDS),
}
LIBRARY_TOTALS = {
    'tutorials': EXPECTED_INITIAL_TUTORIALS,
    'sponsored-view': EXPECTED_INITIAL_SPONSORED_ASSESSMENTS,
    'main-contest': EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS,
}
NAMESPACE = uuid.UUID('ac0b702e-b758-4c29-a101-268ba66ad8db')
MODEL_BY_LIBRARY = {
    'tutorials': Tutorial,
    'sponsored-view': SponsoredViewAssessment,
    'main-contest': AssessmentSchedule,
}
SENSITIVE_FIELDS = {'Medical and Health', 'Law and Society'}


class Command(BaseCommand):
    help = 'Validate or append the complete bundled ApexStratos assessment libraries.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Append validated records to the database. Omit for a no-write dry run.',
        )
        parser.add_argument(
            '--publish',
            action='store_true',
            help='Publish validated content for eight fields; Medical and Health / Law and Society stay drafts.',
        )

    def handle(self, *args, **options):
        if options['publish'] and not options['apply']:
            raise CommandError('--publish requires --apply.')
        root = Path(settings.BASE_DIR) / 'content_packs' / 'original'
        manifest_path = root / 'manifest.json'
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except OSError as error:
            raise CommandError(f'Cannot read content manifest {manifest_path}: {error}') from error
        except json.JSONDecodeError as error:
            raise CommandError(f'Content manifest is not valid JSON: {error}') from error

        packs = self._validate_manifest(root, manifest)
        if not options['apply']:
            self.stdout.write(
                f'Validated {len(packs)} content packs: '
                f'{EXPECTED_INITIAL_TUTORIALS} tutorials, '
                f'{EXPECTED_INITIAL_SPONSORED_ASSESSMENTS} Sponsored View assessments, '
                f'{EXPECTED_INITIAL_MAIN_CONTEST_ASSESSMENTS} Main Contest assessments. '
                'No database records were changed.'
            )
            return

        with transaction.atomic():
            for entry, path, _payload in packs:
                command_output = StringIO()
                command_args = [
                    '--library', entry['library'],
                    '--file', str(path),
                    '--apply',
                ]
                call_command(
                    'import_apexstratos_assessments',
                    *command_args,
                    stdout=command_output,
                )
                output = command_output.getvalue().strip()
                self.stdout.write(f'{entry["library"]} / {entry["field"]}: {output}')
                if options['publish'] and entry['field'] not in SENSITIVE_FIELDS:
                    self._publish_pack(entry, _payload)
                elif options['publish']:
                    self.stdout.write(
                        f'{entry["library"]} / {entry["field"]}: kept as draft pending qualified human review.'
                    )

    @classmethod
    def _publish_pack(cls, entry, payload):
        model = MODEL_BY_LIBRARY[entry['library']]
        namespace = uuid.uuid5(NAMESPACE, entry['library'])
        published_at = timezone.now()
        for item in payload['assessments']:
            assessment_id = uuid.uuid5(namespace, item['external_id'])
            assessment = model.objects.get(pk=assessment_id)
            if assessment.field in SENSITIVE_FIELDS:
                raise CommandError(
                    f'{assessment.field} content cannot be published without qualified human review.'
                )
            if assessment.status == 'published':
                if assessment.attempts.exists():
                    continue
            elif assessment.status != 'draft':
                raise CommandError(
                    f'{assessment.imported_external_id} is {assessment.status}; '
                    'only validated draft content can be published by this command.'
                )
            elif assessment.attempts.exists():
                raise CommandError(
                    f'{assessment.imported_external_id} has historical attempts; '
                    'the command will not change its status.'
                )

            complete = {
                'tutorials': tutorial_is_complete,
                'sponsored-view': sponsored_view_is_complete,
                'main-contest': contest_is_complete,
            }[entry['library']](assessment)
            if not complete:
                raise CommandError(
                    f'{assessment.imported_external_id} failed publication completeness validation.'
                )
            if entry['library'] == 'tutorials':
                assessment.validate_for_publication()
            if assessment.status != 'published':
                assessment.status = 'published'
                assessment.published_at = published_at
                assessment.save(update_fields=('status', 'published_at', 'updated_at'))

    @staticmethod
    def _validate_manifest(root, manifest):
        if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
            raise CommandError('Content manifest must be a JSON object with schema_version: 1.')
        entries = manifest.get('packs')
        if not isinstance(entries, list):
            raise CommandError('Content manifest packs must be a list.')

        expected_pairs = {
            (library, field)
            for library in LIBRARY_COUNTS
            for field in CAPABILITY_FIELDS
        }
        seen_pairs = set()
        seen_files = set()
        totals = {library: 0 for library in LIBRARY_COUNTS}
        validated = []
        for index, entry in enumerate(entries):
            location = f'packs[{index}]'
            if not isinstance(entry, dict):
                raise CommandError(f'{location}: expected an object.')
            library = entry.get('library')
            field = entry.get('field')
            relative_path = entry.get('file')
            expected_count = entry.get('assessments')
            pair = (library, field)
            if library not in LIBRARY_COUNTS or field not in CAPABILITY_FIELDS:
                raise CommandError(f'{location}: invalid library or official study area.')
            if pair in seen_pairs:
                raise CommandError(f'{location}: duplicate library/study-area manifest entry {pair!r}.')
            seen_pairs.add(pair)
            if expected_count != LIBRARY_COUNTS[library]:
                raise CommandError(
                    f'{location}: expected {LIBRARY_COUNTS[library]} assessments for {library} / {field}.'
                )
            if not isinstance(relative_path, str) or not relative_path.strip():
                raise CommandError(f'{location}.file: expected a relative JSON pack path.')
            relative = Path(relative_path)
            if relative.is_absolute() or '..' in relative.parts:
                raise CommandError(f'{location}.file: path must stay inside the content-pack directory.')
            path = (root / relative).resolve()
            if root.resolve() not in path.parents or path in seen_files:
                raise CommandError(f'{location}.file: path is outside the content-pack directory or duplicated.')
            seen_files.add(path)
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except OSError as error:
                raise CommandError(f'Cannot read content pack {path}: {error}') from error
            except json.JSONDecodeError as error:
                raise CommandError(f'Content pack {path} is not valid JSON: {error}') from error
            try:
                assessments = _validate_pack(payload, library)
            except CommandError as error:
                raise CommandError(f'Content pack {path} failed validation: {error}') from error
            if len(assessments) != expected_count:
                raise CommandError(
                    f'{path}: expected {expected_count} {library} assessments, found {len(assessments)}.'
                )
            if any(assessment['field'] != field for assessment in assessments):
                raise CommandError(f'{path}: all assessments must map to {field}.')
            totals[library] += len(assessments)
            validated.append((entry, path, payload))

        if seen_pairs != expected_pairs:
            missing = sorted(expected_pairs - seen_pairs)
            extra = sorted(seen_pairs - expected_pairs)
            raise CommandError(f'Content manifest must cover every library/study area; missing={missing}, extra={extra}.')
        for library, expected_total in LIBRARY_TOTALS.items():
            if totals[library] != expected_total:
                raise CommandError(
                    f'Content manifest has {totals[library]} {library} assessments; expected {expected_total}.'
                )
        return validated
