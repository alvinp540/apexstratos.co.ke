import json
from pathlib import Path
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cohorts.management.commands.import_apexstratos_assessments import _validate_pack
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
class Command(BaseCommand):
    help = 'Validate or append the complete bundled ApexStratos assessment libraries.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Append validated records to the database. Omit for a no-write dry run.',
        )
    def handle(self, *args, **options):
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
