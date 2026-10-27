import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cohorts.management.commands.bootstrap_apexstratos_libraries import (
    Command as BootstrapLibrariesCommand,
)


class Command(BaseCommand):
    help = 'Validate and optionally import a limited number of tutorial drafts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            required=True,
            help='Number of validated tutorial drafts to add.',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Append tutorials as drafts. Omit for a no-write dry run.',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        if limit < 1:
            raise CommandError('--limit must be a positive integer.')

        root = Path(settings.BASE_DIR) / 'content_packs' / 'original'
        try:
            manifest = json.loads(
                (root / 'manifest.json').read_text(encoding='utf-8')
            )
        except OSError as error:
            raise CommandError(f'Cannot read tutorial content manifest: {error}') from error
        except json.JSONDecodeError as error:
            raise CommandError(f'Tutorial content manifest is not valid JSON: {error}') from error

        packs, invalid_packs = BootstrapLibrariesCommand._validate_manifest_partial(
            root,
            manifest,
        )
        tutorial_packs = []
        eligible_count = 0
        skipped_conflicts = 0
        for entry, _path, payload in packs:
            if entry['library'] != 'tutorials':
                continue
            selected, conflicts = (
                BootstrapLibrariesCommand._without_existing_schedule_conflicts(
                    entry,
                    payload,
                    preserve=True,
                )
            )
            skipped_conflicts += len(conflicts)
            if selected:
                tutorial_packs.append((entry, payload, selected))
                eligible_count += len(selected)

        if eligible_count < limit:
            raise CommandError(
                f'Requested {limit} tutorials, but only {eligible_count} validated '
                'tutorials are available without conflicting with existing schedule slots. '
                'No records were changed.'
            )

        selected_by_pack = [[] for _ in tutorial_packs]
        selected_count = 0
        while selected_count < limit:
            for index, (_entry, _payload, assessments) in enumerate(tutorial_packs):
                position = len(selected_by_pack[index])
                if position >= len(assessments):
                    continue
                selected_by_pack[index].append(assessments[position])
                selected_count += 1
                if selected_count == limit:
                    break

        action = 'Importing' if options['apply'] else 'Would import'
        self.stdout.write(
            f'{action} {limit} validated tutorials as drafts from '
            f'{eligible_count} eligible bundled tutorials across '
            f'{sum(len(items) > 0 for items in selected_by_pack)} study areas. '
            f'Skipped {skipped_conflicts} tutorials with conflicting schedule slots; '
            f'{sum(entry["library"] == "tutorials" for entry, *_ in invalid_packs)} '
            'tutorial packs failed validation.'
        )

        with TemporaryDirectory(prefix='apex-tutorial-demo-') as temp_dir:
            import_operations = []
            for index, ((entry, payload, _assessments), selected) in enumerate(
                zip(tutorial_packs, selected_by_pack)
            ):
                if not selected:
                    continue
                import_path = Path(temp_dir) / f'tutorial-pack-{index}.json'
                import_path.write_text(
                    json.dumps({
                        'schema_version': payload['schema_version'],
                        'provenance': payload['provenance'],
                        'assessments': selected,
                    }, ensure_ascii=False),
                    encoding='utf-8',
                )
                import_operations.append(import_path)

            if options['apply']:
                with transaction.atomic():
                    for import_path in import_operations:
                        call_command(
                            'import_apexstratos_assessments',
                            '--library',
                            'tutorials',
                            '--file',
                            str(import_path),
                            '--apply',
                            stdout=self.stdout,
                        )
            else:
                for import_path in import_operations:
                    call_command(
                        'import_apexstratos_assessments',
                        '--library',
                        'tutorials',
                        '--file',
                        str(import_path),
                        stdout=self.stdout,
                    )

        if not options['apply']:
            self.stdout.write('Dry run only; no database records were changed.')
