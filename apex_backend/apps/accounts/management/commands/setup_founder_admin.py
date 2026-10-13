from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User


FOUNDER_EMAIL = 'lekishonlincoln@gmail.com'
FOUNDER_USERNAME = 'Lincoln'


class Command(BaseCommand):
    help = 'Create or promote the founder admin account, prompting securely for a new password.'

    def handle(self, *args, **options):
        password = getpass('Enter a NEW founder admin password: ')
        confirmation = getpass('Confirm the new password: ')
        if not password or password != confirmation:
            raise CommandError('Passwords were empty or did not match; no account changes were made.')
        if len(password) < 14:
            raise CommandError('Use at least 14 characters for the new password.')

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                email=FOUNDER_EMAIL,
                defaults={'username': FOUNDER_USERNAME, 'role': 'admin'},
            )
            user.username = FOUNDER_USERNAME
            user.role = 'admin'
            user.is_staff = True
            user.is_active = True
            user.set_password(password)
            user.save(update_fields=['username', 'role', 'is_staff', 'is_active', 'password'])

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} founder admin {FOUNDER_EMAIL} ({FOUNDER_USERNAME}).'))
