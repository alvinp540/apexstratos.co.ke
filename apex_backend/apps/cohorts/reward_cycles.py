from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.utils import send_notification
from .models import (
    SponsoredViewAssessment,
    SponsoredViewAttempt,
    SponsoredViewDailySettlement,
    SponsoredViewPayment,
    SponsoredViewRewardAward,
    SponsoredViewRewardClaim,
    SponsoredViewRewardCycle,
    SponsoredViewRewardCycleEntry,
)
from .weekly_schedule import EAT


ENTRY_FEE_KES = 20
CYCLE_SIZE = 10
STANDARD_AWARD_KES = 100


def _rank_key(entry):
    return (-entry.score, entry.submitted_at, str(entry.user_id))


def _finish_cycle(cycle):
    """Finalize a full cycle inside the caller's transaction."""
    if cycle.status not in {'full', 'failed'}:
        return cycle
    entries = list(
        cycle.entries.select_for_update().select_related('payment', 'attempt', 'user')
        .filter(status='eligible').order_by('submitted_at', 'id')
    )
    valid_entries = []
    for entry in entries:
        attempt = entry.attempt
        payment = entry.payment
        valid = (
            payment.status == 'verified'
            and payment.amount_kes == ENTRY_FEE_KES
            and payment.till_number == SponsoredViewPayment.PAYMENT_TILL_NUMBER
            and payment.verified_at is not None
            and attempt.status in {'graded', 'timed_out'}
            and not attempt.is_flagged
            and attempt.score is not None
            and attempt.submitted_at is not None
            and attempt.score == entry.score
        )
        if valid:
            valid_entries.append(entry)
        else:
            entry.status = 'ineligible'
            entry.save(update_fields=('status',))

    cycle.eligible_completion_count = len(valid_entries)
    if len(valid_entries) < cycle.target_completion_count:
        cycle.status = 'open'
        cycle.full_at = None
        cycle.error_message = 'One or more entries became ineligible before finalization.'
        cycle.save(update_fields=('eligible_completion_count', 'status', 'full_at', 'error_message'))
        return cycle
    if len(valid_entries) != cycle.target_completion_count:
        raise ValueError('A reward cycle cannot be finalized with more than its target entries.')

    assessment = cycle.assessment
    ranked = sorted(valid_entries, key=_rank_key)
    eligible_ranked = [entry for entry in ranked if entry.score >= assessment.reward_minimum_score]
    winner = eligible_ranked[0] if eligible_ranked else None
    for index, entry in enumerate(ranked, start=1):
        entry.rank = index
        entry.save(update_fields=('rank',))

    now = timezone.now()
    local_date = now.astimezone(EAT).date()
    gross_revenue = cycle.target_completion_count * cycle.participation_fee_kes
    platform_allocation = gross_revenue // 2
    rewards_allocation = gross_revenue - platform_allocation
    award_amount = STANDARD_AWARD_KES if winner and rewards_allocation >= STANDARD_AWARD_KES else 0
    reserve = rewards_allocation - award_amount
    cycle.status = 'finalizing'
    cycle.save(update_fields=('status', 'eligible_completion_count'))

    settlement = SponsoredViewDailySettlement.objects.create(
        assessment=assessment,
        capability=cycle.capability,
        settlement_date=local_date,
        period_start=min(entry.submitted_at for entry in valid_entries),
        period_end=max(entry.submitted_at for entry in valid_entries),
        participation_fee_kes=cycle.participation_fee_kes,
        eligible_participant_count=len(valid_entries),
        total_revenue_kes=gross_revenue,
        platform_share_kes=platform_allocation,
        rewards_budget_kes=rewards_allocation,
        primary_winner_count=1 if award_amount else 0,
        secondary_winner_count=0,
        awarded_total_kes=award_amount,
        unallocated_reserve_kes=reserve,
        criteria_snapshot={
            'cycle_id': str(cycle.id),
            'cycle_number': cycle.cycle_number,
            'target_completions': cycle.target_completion_count,
            'minimum_score': assessment.reward_minimum_score,
            'ranking': ['score descending', 'submitted_at ascending', 'user UUID ascending'],
            'payment_source': 'admin-verified SponsoredViewPayment, KES 20, company Till 1598106',
            'eligible_attempts': ['graded', 'timed_out'],
            'allocation': '50% platform / 50% rewards',
            'winner_user_id': str(winner.user_id) if award_amount else None,
        },
        status='finalized',
        attempt_count=cycle.finalization_attempt_count,
        idempotency_key=f'sponsored-cycle:{cycle.id}',
        reward_cycle=cycle,
        finalized_at=now,
    )

    cycle.winner = winner.user if award_amount else None
    cycle.ranking_snapshot = [{
        'rank': index,
        'user_id': str(entry.user_id),
        'attempt_id': str(entry.attempt_id),
        'payment_id': str(entry.payment_id),
        'payment_reference': entry.payment.payment_reference,
        'score': entry.score,
        'submitted_at': entry.submitted_at.isoformat(),
        'winner': bool(award_amount and winner.id == entry.id),
        'eligible_for_award': entry.score >= assessment.reward_minimum_score,
    } for index, entry in enumerate(ranked, start=1)]
    cycle.gross_revenue_kes = gross_revenue
    cycle.platform_allocation_kes = platform_allocation
    cycle.rewards_allocation_kes = rewards_allocation
    cycle.award_amount_kes = award_amount
    cycle.settlement_status = 'finalized'
    cycle.payout_status = 'claim_required' if award_amount else 'not_awarded'
    cycle.finalized_at = now
    cycle.error_message = '' if award_amount else 'No participant met the published minimum merit score; rewards allocation retained in reserve.'
    cycle.status = 'finalized' if award_amount else 'exception'
    cycle.save(update_fields=(
        'winner', 'ranking_snapshot', 'gross_revenue_kes', 'platform_allocation_kes',
        'rewards_allocation_kes', 'award_amount_kes', 'settlement_status',
        'payout_status', 'finalization_attempt_count', 'finalized_at', 'error_message', 'status',
    ))

    if award_amount:
        SponsoredViewRewardAward.objects.create(
            settlement=settlement,
            reward_cycle=cycle,
            user=winner.user,
            payment=winner.payment,
            amount_kes=award_amount,
            score=winner.score,
            rank=1,
            selection='primary',
            eligibility_snapshot={
                'cycle_id': str(cycle.id),
                'cycle_number': cycle.cycle_number,
                'attempt_id': str(winner.attempt_id),
                'attempt_submitted_at': winner.submitted_at.isoformat(),
                'minimum_score': assessment.reward_minimum_score,
            },
        )
        award = SponsoredViewRewardAward.objects.get(reward_cycle=cycle)
        SponsoredViewRewardClaim.objects.create(award=award, user=winner.user)
        send_notification(
            user=winner.user,
            notification_type='payment',
            title='You won a KES 100 Sponsored View reward',
            message=(
                f'You ranked first in reward cycle {cycle.cycle_number} for '
                f'{assessment.title} ({cycle.capability}) and won KES 100. '
                'Submit a claim to begin payout review.'
            ),
            action_url='/rewards',
            metadata={
                'award_id': str(award.id),
                'cycle_id': str(cycle.id),
                'cycle_number': cycle.cycle_number,
            },
        )
    else:
        for administrator in User.objects.filter(is_active=True, role='admin'):
            send_notification(
                user=administrator,
                notification_type='payment',
                title='Sponsored View reward cycle needs review',
                message=(
                    f'Cycle {cycle.cycle_number} for {assessment.title} ({cycle.capability}) '
                    'reached ten completions with no participant meeting the published minimum score. '
                    'The KES 100 rewards allocation remains in reserve.'
                ),
                action_url='/admin',
                metadata={'cycle_id': str(cycle.id)},
            )

    SponsoredViewRewardCycle.objects.get_or_create(
        assessment=assessment,
        cycle_number=cycle.cycle_number + 1,
        defaults={'capability': cycle.capability},
    )
    return cycle


def finalize_sponsored_reward_cycle(cycle_id):
    """Retry a full or failed cycle; writes either all settlement records or none."""
    with transaction.atomic():
        assessment_id = SponsoredViewRewardCycle.objects.values_list('assessment_id', flat=True).get(id=cycle_id)
        SponsoredViewAssessment.objects.select_for_update().get(id=assessment_id)
        cycle = SponsoredViewRewardCycle.objects.select_for_update().select_related('assessment').get(id=cycle_id)
        if cycle.status in {'finalized', 'exception'}:
            return cycle
        if cycle.status not in {'full', 'failed'}:
            return cycle
        cycle.status = 'finalizing'
        cycle.finalization_attempt_count += 1
        cycle.error_message = ''
        cycle.save(update_fields=('status', 'finalization_attempt_count', 'error_message'))
        try:
            with transaction.atomic():
                cycle = SponsoredViewRewardCycle.objects.select_for_update().select_related('assessment').get(id=cycle_id)
                # _finish_cycle handles records and notification creation atomically.
                cycle.status = 'full'
                cycle.save(update_fields=('status',))
                result = _finish_cycle(cycle)
        except Exception as error:
            cycle = SponsoredViewRewardCycle.objects.select_for_update().get(id=cycle_id)
            cycle.status = 'failed'
            cycle.error_message = str(error)[:5000]
            cycle.save(update_fields=('status', 'error_message'))
            return cycle
        return result


@transaction.atomic
def record_sponsored_view_completion(attempt_id):
    """Assign one finalized, verified participation to its assessment's sequential cycle."""
    attempt = SponsoredViewAttempt.objects.select_for_update().select_related(
        'assessment', 'payment', 'user',
    ).get(id=attempt_id)
    if (
        attempt.status not in {'graded', 'timed_out'}
        or attempt.is_flagged
        or attempt.score is None
        or attempt.submitted_at is None
        or attempt.payment.status != 'verified'
        or attempt.payment.amount_kes != ENTRY_FEE_KES
        or attempt.payment.till_number != SponsoredViewPayment.PAYMENT_TILL_NUMBER
        or attempt.payment.user_id != attempt.user_id
        or attempt.payment.assessment_id != attempt.assessment_id
    ):
        return None

    assessment = SponsoredViewAssessment.objects.select_for_update().get(id=attempt.assessment_id)
    existing = SponsoredViewRewardCycleEntry.objects.select_related('cycle').filter(attempt=attempt).first()
    if existing:
        cycle = existing.cycle
        if cycle.status in {'full', 'failed'}:
            return finalize_sponsored_reward_cycle(cycle.id)
        return cycle

    latest = SponsoredViewRewardCycle.objects.select_for_update().filter(
        assessment=assessment,
    ).order_by('-cycle_number').first()
    if latest and latest.status in {'full', 'failed'}:
        finalize_sponsored_reward_cycle(latest.id)
        latest.refresh_from_db()
    if latest and latest.status == 'failed':
        # Preserve this completion for a later retry rather than assigning it to a
        # cycle whose preceding ten entries have not finalized.
        return latest
    if latest and latest.status == 'open':
        cycle = latest
    elif latest:
        cycle, _ = SponsoredViewRewardCycle.objects.get_or_create(
            assessment=assessment,
            cycle_number=latest.cycle_number + 1,
            defaults={'capability': assessment.field},
        )
    else:
        cycle, _ = SponsoredViewRewardCycle.objects.get_or_create(
            assessment=assessment,
            cycle_number=1,
            defaults={'capability': assessment.field},
        )

    if cycle.entries.filter(user_id=attempt.user_id).exists():
        return cycle
    try:
        with transaction.atomic():
            SponsoredViewRewardCycleEntry.objects.create(
                cycle=cycle,
                payment=attempt.payment,
                attempt=attempt,
                user=attempt.user,
                score=attempt.score,
                submitted_at=attempt.submitted_at,
                eligibility_snapshot={
                    'payment_status': attempt.payment.status,
                    'payment_amount_kes': attempt.payment.amount_kes,
                    'payment_till_number': attempt.payment.till_number,
                    'payment_reference': attempt.payment.payment_reference,
                    'payment_transaction_id': attempt.payment.mpesa_transaction_id,
                    'payment_verified_at': attempt.payment.verified_at.isoformat() if attempt.payment.verified_at else None,
                    'attempt_status': attempt.status,
                    'attempt_flagged': attempt.is_flagged,
                    'assessment_id': str(assessment.id),
                    'capability': assessment.field,
                },
            )
    except IntegrityError:
        return cycle

    cycle.eligible_completion_count = cycle.entries.filter(status='eligible').count()
    if cycle.eligible_completion_count >= cycle.target_completion_count:
        cycle.status = 'full'
        cycle.full_at = timezone.now()
        cycle.save(update_fields=('eligible_completion_count', 'status', 'full_at'))
        cycle.refresh_from_db()
        return finalize_sponsored_reward_cycle(cycle.id)
    cycle.save(update_fields=('eligible_completion_count',))
    return cycle


def retry_failed_sponsored_reward_cycles(limit=100):
    cycle_ids = list(
        SponsoredViewRewardCycle.objects.filter(status__in=('full', 'failed'))
        .order_by('assessment_id', 'cycle_number').values_list('id', flat=True)[:limit]
    )
    return [finalize_sponsored_reward_cycle(cycle_id) for cycle_id in cycle_ids]
