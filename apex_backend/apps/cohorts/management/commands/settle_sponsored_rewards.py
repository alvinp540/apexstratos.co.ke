from django.core.management.base import BaseCommand

from apps.cohorts.reward_cycles import retry_failed_sponsored_reward_cycles


class Command(BaseCommand):
    help = 'Retry failed Sponsored View reward cycle finalizations; cycle awards normally finalize on the tenth completion.'

    def handle(self, *args, **options):
        results = retry_failed_sponsored_reward_cycles()
        finalized = sum(1 for cycle in results if cycle.status in {'finalized', 'exception'})
        failed = sum(1 for cycle in results if cycle.status == 'failed')
        self.stdout.write(self.style.SUCCESS(
            f'Retried {len(results)} failed reward cycle(s): {finalized} finalized, {failed} still failed.'
        ))
