"""Outgoing reward payout boundary.

Production providers must implement both transfer and lookup so an ambiguous
timeout can be reconciled before any retry. No live provider is configured by
default; the application must never assume a transfer succeeded.
"""

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


class PayoutProviderNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class PayoutResult:
    status: str
    provider_reference: str = ''
    message: str = ''


class RewardPayoutProvider(Protocol):
    def transfer(self, *, idempotency_key: str, recipient_phone: str, amount_kes: int) -> PayoutResult:
        """Submit or resume a transfer without duplicating an existing request."""

    def lookup(self, *, idempotency_key: str) -> PayoutResult:
        """Resolve a prior transfer after a timeout or ambiguous response."""


class UnconfiguredRewardPayoutProvider:
    def transfer(self, *, idempotency_key: str, recipient_phone: str, amount_kes: int) -> PayoutResult:
        raise PayoutProviderNotConfigured('No outgoing reward payout provider is configured.')

    def lookup(self, *, idempotency_key: str) -> PayoutResult:
        raise PayoutProviderNotConfigured('No outgoing reward payout provider is configured.')


def get_reward_payout_provider() -> RewardPayoutProvider:
    provider_path = getattr(settings, 'REWARD_PAYOUT_PROVIDER', '').strip()
    if not provider_path:
        return UnconfiguredRewardPayoutProvider()
    return import_string(provider_path)()
