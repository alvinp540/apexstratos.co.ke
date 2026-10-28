from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from apps.cohorts.reward_settlement import settle_daily_sponsored_view
from apps.cohorts.weekly_schedule import EAT


class Command(BaseCommand):
    help = 'Settle verified Sponsored View participation for one EAT calendar day.'

    def add_arguments(self, parser):
        parser.add_argument('--date', dest='settlement_date', help='EAT settlement date (YYYY-MM-DD). Defaults to yesterday.')

    def handle(self, *args, **options):
        raw_date = options.get('settlement_date')
        try:
            settlement_date = date.fromisoformat(raw_date) if raw_date else datetime.now(EAT).date() - timedelta(days=1)
        except ValueError as error:
            raise CommandError('--date must use YYYY-MM-DD format.') from error
        results = settle_daily_sponsored_view(settlement_date)
        created = sum(1 for _settlement, is_new in results if is_new)
        self.stdout.write(self.style.SUCCESS(
            f'{created} new settlement(s); {len(results) - created} already finalized for {settlement_date} EAT.'
        ))
