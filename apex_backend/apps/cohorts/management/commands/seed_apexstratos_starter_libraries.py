import json
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cohorts.management.commands.bootstrap_apexstratos_libraries import (
    Command as BootstrapLibrariesCommand,
)
from apps.cohorts.management.commands.import_apexstratos_assessments import _validate_pack


STARTER_PACKS = (
    ('tutorials', 'tutorial.json'),
    ('sponsored-view', 'sponsored-view.json'),
    ('main-contest', 'main-contest.json'),
)


class Command(BaseCommand):
    help = (
        'Validate and optionally publish the original ApexStratos starter assessment '
        'for each student library.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Append and publish the validated starter assessments. Omit for a no-write dry run.',
        )

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR) / 'content_packs' / 'original' / 'starter'
        validated_packs = []
        for library, filename in STARTER_PACKS:
            path = root / filename
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except OSError as error:
                raise CommandError(f'Cannot read starter content pack {path}: {error}') from error
            except json.JSONDecodeError as error:
                raise CommandError(f'Starter content pack {path} is not valid JSON: {error}') from error

            try:
                assessments = _validate_pack(payload, library)
            except CommandError as error:
                raise CommandError(f'Starter content pack {path} failed validation: {error}') from error
            if len(assessments) != 1 or assessments[0]['field'] != 'Software Development':
                raise CommandError(
                    f'{path}: expected exactly one Software Development assessment.'
                )
            validated_packs.append((library, path, payload, assessments[0]))

        if not options['apply']:
            self.stdout.write(
                'Validated one complete assessment for each library: Tutorial, Sponsored View, '
                'and Main Contest. All packs contain ten distinct MCQs and no answer keys are '
                'exposed before submission. No database records were changed.'
            )
            self.stdout.write('Re-run with --apply to append and publish this starter content.')
            return

        published = 0
        with transaction.atomic():
            for library, path, payload, assessment_data in validated_packs:
                import_output = StringIO()
                call_command(
                    'import_apexstratos_assessments',
                    '--library',
                    library,
                    '--file',
                    str(path),
                    '--apply',
                    stdout=import_output,
                )
                self.stdout.write(import_output.getvalue().strip())
                entry = {
                    'library': library,
                    'field': assessment_data['field'],
                }
                BootstrapLibrariesCommand._publish_pack(
                    entry,
                    {'assessments': [assessment_data]},
                )
                published += 1

        self.stdout.write(
            f'Published {published} starter assessments. Re-running is idempotent and preserves existing attempts.'
        )
