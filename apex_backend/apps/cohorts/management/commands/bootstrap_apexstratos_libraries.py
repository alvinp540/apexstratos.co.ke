import json
import uuid
from pathlib import Path
from io import StringIO
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cohorts.management.commands.import_apexstratos_assessments import (
    NAMESPACE as IMPORT_NAMESPACE,
    _validate_pack,
)
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
        parser.add_argument(
            '--allow-partial',
            action='store_true',
            help='Import complete valid packs and report invalid packs instead of aborting the entire library.',
        )
        parser.add_argument(
            '--preserve-existing-slots',
            action='store_true',
            help='Skip manifest assessments whose schedule slots are occupied by different existing records.',
        )
        parser.add_argument(
            '--report-json',
            type=Path,
            help='Write the validation and import counts to a JSON report at this path.',
        )

    def handle(self, *args, **options):
        if options['publish'] and not options['apply']:
            raise CommandError('--publish requires --apply.')
        if options['preserve_existing_slots'] and not options['allow_partial']:
            raise CommandError('--preserve-existing-slots requires --allow-partial.')
        root = Path(settings.BASE_DIR) / 'content_packs' / 'original'
        manifest_path = root / 'manifest.json'
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except OSError as error:
            raise CommandError(f'Cannot read content manifest {manifest_path}: {error}') from error
        except json.JSONDecodeError as error:
            raise CommandError(f'Content manifest is not valid JSON: {error}') from error

        if options['allow_partial']:
            packs, invalid_packs = self._validate_manifest_partial(root, manifest)
        else:
            packs = self._validate_manifest(root, manifest)
            invalid_packs = []

        report = {
            'mode': 'apply' if options['apply'] else 'dry-run',
            'partial_mode': options['allow_partial'],
            'manifest_packs': len(manifest.get('packs', [])) if isinstance(manifest, dict) else 0,
            'valid_packs': len(packs),
            'invalid_packs': [],
            'packs': [],
            'libraries': {
                library: {
                    'inserted': 0,
                    'would_insert': 0,
                    'updated': 0,
                    'skipped_existing': 0,
                    'skipped_schedule_conflict': 0,
                    'failed': 0,
                    'published': 0,
                    'draft': 0,
                }
                for library in LIBRARY_COUNTS
            },
        }
        for entry, _path, _payload, error in invalid_packs:
            library = entry['library']
            failed_count = entry['assessments']
            report['libraries'][library]['failed'] += failed_count
            invalid_report = {
                'library': library,
                'field': entry['field'],
                'file': entry['file'],
                'failed_assessments': failed_count,
                'error': error,
            }
            report['invalid_packs'].append(invalid_report)
            report['packs'].append(dict(invalid_report, status='invalid'))
            self.stderr.write(
                f'INVALID {library} / {entry["field"]} / {entry["file"]}: '
                f'{failed_count} assessment(s) not imported: {error}'
            )

        with TemporaryDirectory(prefix='apexstratos-import-') as temp_dir:
            for entry, path, payload in packs:
                library_report = report['libraries'][entry['library']]
                pack_report = {
                    'library': entry['library'],
                    'field': entry['field'],
                    'file': entry['file'],
                    'valid_assessments': len(payload['assessments']),
                    'inserted': 0,
                    'would_insert': 0,
                    'updated': 0,
                    'skipped_existing': 0,
                    'skipped_schedule_conflict': 0,
                    'failed': 0,
                    'published': 0,
                    'draft': 0,
                    'schedule_conflicts': [],
                }
                report['packs'].append(pack_report)
                selected, conflicts = self._without_existing_schedule_conflicts(
                    entry,
                    payload,
                    preserve=options['preserve_existing_slots'],
                )
                for conflict in conflicts:
                    library_report['skipped_schedule_conflict'] += 1
                    pack_report['skipped_schedule_conflict'] += 1
                    pack_report['schedule_conflicts'].append(conflict)
                    self.stdout.write(
                        f'SKIPPED SLOT {entry["library"]} / {entry["field"]} / '
                        f'{conflict["external_id"]}: preserved existing '
                        f'{conflict["existing_id"]} ({conflict["existing_title"]}, '
                        f'{conflict["attempt_count"]} attempt(s)).'
                    )

                if not selected:
                    continue
                if not options['apply']:
                    library_report['would_insert'] += len(selected)
                    pack_report['would_insert'] += len(selected)
                    continue

                selected_payload = {
                    'schema_version': payload['schema_version'],
                    'provenance': payload['provenance'],
                    'assessments': selected,
                }
                import_path = Path(temp_dir) / f'{entry["library"]}-{len(report["invalid_packs"])}-{entry["field"]}.json'
                import_path.write_text(
                    json.dumps(selected_payload, ensure_ascii=False),
                    encoding='utf-8',
                )
                model = MODEL_BY_LIBRARY[entry['library']]
                assessment_ids = self._assessment_ids(entry['library'], selected)
                existing_ids = set(
                    str(value)
                    for value in model.objects.filter(id__in=assessment_ids).values_list('id', flat=True)
                )
                command_output = StringIO()
                try:
                    with transaction.atomic():
                        call_command(
                            'import_apexstratos_assessments',
                            '--library',
                            entry['library'],
                            '--file',
                            str(import_path),
                            '--apply',
                            stdout=command_output,
                        )
                        imported_payload = dict(selected_payload, assessments=selected)
                        if options['publish'] and entry['field'] not in SENSITIVE_FIELDS:
                            self._publish_pack(entry, imported_payload)
                        elif options['publish']:
                            self.stdout.write(
                                f'{entry["library"]} / {entry["field"]}: kept as draft pending qualified human review.'
                            )
                except (CommandError, IntegrityError, ValidationError) as error:
                    library_report['failed'] += len(selected)
                    pack_report['failed'] += len(selected)
                    pack_report['status'] = 'failed'
                    self.stderr.write(
                        f'FAILED {entry["library"]} / {entry["field"]} / {entry["file"]}: '
                        f'{len(selected)} assessment(s) rolled back: {error}'
                    )
                    continue

                persisted_ids = set(
                    str(value)
                    for value in model.objects.filter(id__in=assessment_ids).values_list('id', flat=True)
                )
                created = len(persisted_ids - existing_ids)
                unchanged = len(persisted_ids & existing_ids)
                missing = len(assessment_ids) - len(persisted_ids)
                library_report['inserted'] += created
                library_report['skipped_existing'] += unchanged
                pack_report['inserted'] += created
                pack_report['skipped_existing'] += unchanged
                if missing:
                    library_report['failed'] += missing
                    pack_report['failed'] += missing
                    pack_report['status'] = 'failed'
                    self.stderr.write(
                        f'FAILED {entry["library"]} / {entry["field"]}: '
                        f'{missing} assessment(s) were not persisted.'
                    )
                if options['publish']:
                    published = model.objects.filter(
                        id__in=assessment_ids,
                        status='published',
                    ).count()
                    library_report['published'] += published
                    library_report['draft'] += len(persisted_ids) - published
                    pack_report['published'] = published
                    pack_report['draft'] = len(persisted_ids) - published
                pack_report.setdefault(
                    'status',
                    'imported' if created else 'unchanged',
                )
                self.stdout.write(
                    f'{entry["library"]} / {entry["field"]}: '
                    f'{command_output.getvalue().strip()}'
                )

        if not options['apply']:
            self.stdout.write('Dry run only; no database records were changed.')
        self.stdout.write(
            f'Assessment import totals: valid_packs={report["valid_packs"]}, '
            f'invalid_packs={len(report["invalid_packs"])}, '
            f'inserted={sum(item["inserted"] for item in report["libraries"].values())}, '
            f'would_insert={sum(item["would_insert"] for item in report["libraries"].values())}, '
            f'updated={sum(item["updated"] for item in report["libraries"].values())}, '
            f'skipped_existing={sum(item["skipped_existing"] for item in report["libraries"].values())}, '
            f'skipped_schedule_conflict={sum(item["skipped_schedule_conflict"] for item in report["libraries"].values())}, '
            f'failed={sum(item["failed"] for item in report["libraries"].values())}.'
        )
        for library, counts in report['libraries'].items():
            self.stdout.write(
                f'{library}: inserted={counts["inserted"]}, updated={counts["updated"]}, '
                f'skipped_existing={counts["skipped_existing"]}, '
                f'skipped_schedule_conflict={counts["skipped_schedule_conflict"]}, '
                f'failed={counts["failed"]}, published={counts["published"]}, draft={counts["draft"]}.'
            )
        if options['report_json']:
            report_path = options['report_json'].resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8',
            )
            self.stdout.write(f'Wrote import report: {report_path}')

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

    @classmethod
    def _validate_manifest_partial(cls, root, manifest):
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
        invalid = []
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
                assessments = _validate_pack(payload, library)
                if len(assessments) != expected_count:
                    raise CommandError(
                        f'{path}: expected {expected_count} {library} assessments, found {len(assessments)}.'
                    )
                if any(assessment['field'] != field for assessment in assessments):
                    raise CommandError(f'{path}: all assessments must map to {field}.')
            except (OSError, json.JSONDecodeError, CommandError) as error:
                invalid.append((entry, path, None, str(error)))
                continue
            totals[library] += len(assessments)
            validated.append((entry, path, payload))

        if seen_pairs != expected_pairs:
            missing = sorted(expected_pairs - seen_pairs)
            extra = sorted(seen_pairs - expected_pairs)
            raise CommandError(
                f'Content manifest must cover every library/study area; missing={missing}, extra={extra}.'
            )
        for library, expected_total in LIBRARY_TOTALS.items():
            if totals[library] > expected_total:
                raise CommandError(
                    f'Content manifest has {totals[library]} valid {library} assessments; '
                    f'expected at most {expected_total}.'
                )
        return validated, invalid

    @staticmethod
    def _assessment_ids(library, assessments):
        namespace = uuid.uuid5(IMPORT_NAMESPACE, library)
        return [
            uuid.uuid5(namespace, item['external_id'])
            for item in assessments
        ]

    @classmethod
    def _without_existing_schedule_conflicts(cls, entry, payload, preserve):
        model = MODEL_BY_LIBRARY[entry['library']]
        kept = []
        conflicts = []
        for item in payload['assessments']:
            stable_id = cls._assessment_ids(entry['library'], [item])[0]
            if model.objects.filter(pk=stable_id).exists():
                kept.append(item)
                continue
            week = item['week']
            month, local_week = divmod(week - 1, 4)
            schedule = {'field': item['field']}
            if entry['library'] == 'sponsored-view':
                schedule.update({'week': week, 'slot': item['slot']})
            else:
                schedule.update({
                    'month': month + 1,
                    'week': local_week + 1,
                    'day': item['day'],
                    'daily_slot' if entry['library'] == 'tutorials' else 'assessment_slot': item['slot'],
                })
            existing = model.objects.filter(**schedule).first()
            if not existing:
                kept.append(item)
                continue
            if not preserve:
                raise CommandError(
                    f'{entry["library"]} assessment {item["external_id"]!r} conflicts with existing '
                    f'{existing.pk} in the same schedule slot; use --preserve-existing-slots only '
                    'after reviewing the existing record.'
                )
            conflicts.append({
                'external_id': item['external_id'],
                'existing_id': str(existing.pk),
                'existing_title': existing.title,
                'attempt_count': existing.attempts.count(),
            })
        return kept, conflicts
