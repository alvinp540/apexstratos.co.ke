from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.notifications.utils import send_notification
from .models import (
    SponsoredViewAssessment,
    SponsoredViewDailySettlement,
    SponsoredViewPayment,
    SponsoredViewAttempt,
    SponsoredViewRewardAward,
)
from .weekly_schedule import EAT


ENTRY_FEE_KES = 20
STANDARD_AWARD_KES = 100


def settlement_window(local_date):
    start = timezone.make_aware(datetime.combine(local_date, time.min), EAT)
    return start, start + timedelta(days=1)


def _rank_key(candidate):
    attempt = candidate['attempt']
    return (-attempt.score, attempt.submitted_at, str(candidate['user_id']))


def settle_sponsored_view_assessment(assessment_id, local_date):
    try:
        return _settle_sponsored_view_assessment(assessment_id, local_date)
    except Exception as error:
        assessment = SponsoredViewAssessment.objects.filter(id=assessment_id).first()
        if assessment:
            start, end = settlement_window(local_date)
            key = f'sponsored-view:{assessment_id}:{local_date.isoformat()}:EAT'
            with transaction.atomic():
                settlement = SponsoredViewDailySettlement.objects.select_for_update().filter(
                    idempotency_key=key,
                ).first()
                if settlement and settlement.status == 'finalized':
                    raise
                if settlement:
                    settlement.status = 'failed'
                    settlement.attempt_count += 1
                    settlement.error_message = str(error)[:5000]
                    settlement.save(update_fields=('status', 'attempt_count', 'error_message'))
                else:
                    SponsoredViewDailySettlement.objects.create(
                        assessment=assessment,
                        capability=assessment.field,
                        settlement_date=local_date,
                        period_start=start,
                        period_end=end,
                        status='failed',
                        attempt_count=1,
                        error_message=str(error)[:5000],
                        idempotency_key=key,
                    )
        raise


@transaction.atomic
def _settle_sponsored_view_assessment(assessment_id, local_date):
    assessment = SponsoredViewAssessment.objects.select_for_update().get(id=assessment_id)
    start, end = settlement_window(local_date)
    key = f'sponsored-view:{assessment_id}:{local_date.isoformat()}:EAT'
    existing = SponsoredViewDailySettlement.objects.filter(idempotency_key=key).first()
    if existing and existing.status == 'finalized':
        return existing, False

    payments = SponsoredViewPayment.objects.filter(
        assessment=assessment,
        status='verified',
        amount_kes=ENTRY_FEE_KES,
        verified_at__gte=start,
        verified_at__lt=end,
    ).select_related('user').prefetch_related('attempt').order_by('verified_at', 'id')

    # Every distinct verified payment with a completed attempt contributes revenue.
    # A student is ranked only once using their best score, preventing duplicate awards.
    eligible_entries = []
    candidates_by_user = {}
    for payment in payments:
        try:
            attempt = payment.attempt
        except SponsoredViewAttempt.DoesNotExist:
            continue
        if (
            not attempt
            or attempt.status not in {'graded', 'timed_out'}
            or attempt.is_flagged
            or attempt.score is None
            or not attempt.submitted_at
            or not (start <= attempt.submitted_at < end)
        ):
            continue
        candidate = {
            'payment': payment,
            'attempt': attempt,
            'user_id': payment.user_id,
        }
        eligible_entries.append(candidate)
        previous = candidates_by_user.get(payment.user_id)
        if previous is None or _rank_key(candidate) < _rank_key(previous):
            candidates_by_user[payment.user_id] = candidate

    candidates = sorted(candidates_by_user.values(), key=_rank_key)
    revenue = len(eligible_entries) * ENTRY_FEE_KES
    platform_share = revenue // 2
    rewards_budget = revenue - platform_share
    award_slots = rewards_budget // STANDARD_AWARD_KES
    minimum_score = assessment.reward_minimum_score
    primary_score = max(minimum_score, assessment.reward_primary_score)
    primary = [item for item in candidates if item['attempt'].score >= primary_score]
    secondary = [item for item in candidates if minimum_score <= item['attempt'].score < primary_score]
    selected_primary = primary[:award_slots]
    remaining_slots = award_slots - len(selected_primary)
    selected_secondary = secondary[:remaining_slots]
    selected_ids = {
        item['payment'].id: ('primary', rank + 1)
        for rank, item in enumerate(selected_primary)
    }
    selected_ids.update({
        item['payment'].id: ('secondary', len(selected_primary) + rank + 1)
        for rank, item in enumerate(selected_secondary)
    })

    settlement_values = {
        'assessment': assessment,
        'capability': assessment.field,
        'settlement_date': local_date,
        'period_start': start,
        'period_end': end,
        'eligible_participant_count': len(eligible_entries),
        'total_revenue_kes': revenue,
        'platform_share_kes': platform_share,
        'rewards_budget_kes': rewards_budget,
        'primary_winner_count': len(selected_primary),
        'secondary_winner_count': len(selected_secondary),
        'awarded_total_kes': (len(selected_primary) + len(selected_secondary)) * STANDARD_AWARD_KES,
        'unallocated_reserve_kes': rewards_budget - (len(selected_primary) + len(selected_secondary)) * STANDARD_AWARD_KES,
        'criteria_snapshot': {
            'minimum_score': minimum_score,
            'primary_score': primary_score,
            'ranking': ['score descending', 'submitted_at ascending', 'user UUID ascending'],
            'payment_source': 'admin-verified SponsoredViewPayment',
            'eligible_attempt': 'graded, unflagged, submitted within EAT day',
        },
        'status': 'finalized',
        'error_message': existing.error_message if existing else '',
        'attempt_count': existing.attempt_count + 1 if existing else 1,
        'finalized_at': timezone.now(),
    }
    if existing:
        for field, value in settlement_values.items():
            setattr(existing, field, value)
        existing.save()
        settlement = existing
    else:
        settlement = SponsoredViewDailySettlement.objects.create(
            **settlement_values,
            idempotency_key=key,
        )

    rank_by_payment = {item['payment'].id: rank for rank, item in enumerate(candidates, start=1)}
    for candidate in candidates:
        payment = candidate['payment']
        selected = selected_ids.get(payment.id)
        if not selected:
            continue
        selection, selection_rank = selected
        award = SponsoredViewRewardAward.objects.create(
            settlement=settlement,
            user_id=candidate['user_id'],
            payment=payment,
            amount_kes=STANDARD_AWARD_KES,
            score=candidate['attempt'].score,
            rank=rank_by_payment[payment.id],
            selection=selection,
            eligibility_snapshot={
                'selection_rank': selection_rank,
                'minimum_score': minimum_score,
                'primary_score': primary_score,
                'attempt_id': str(candidate['attempt'].id),
                'attempt_submitted_at': candidate['attempt'].submitted_at.isoformat(),
            },
        )
        from .models import SponsoredViewRewardClaim
        SponsoredViewRewardClaim.objects.create(award=award, user_id=candidate['user_id'])
        send_notification(
            user=payment.user,
            notification_type='payment',
            title='Congratulations! You earned a KES 100 reward.',
            message=(
                f'You qualified for a KES 100 reward in {assessment.title} '
                f'({assessment.field}) for {local_date.isoformat()}. Submit a claim to begin payout review.'
            ),
            action_url='/rewards',
            metadata={
                'award_id': str(award.id),
                'settlement_id': str(settlement.id),
                'selection': selection,
            },
        )
    return settlement, True


def settle_daily_sponsored_view(local_date):
    start, end = settlement_window(local_date)
    assessment_ids = SponsoredViewPayment.objects.filter(
        status='verified', verified_at__gte=start, verified_at__lt=end,
    ).values_list('assessment_id', flat=True).distinct()
    results = []
    for assessment_id in assessment_ids:
        results.append(settle_sponsored_view_assessment(assessment_id, local_date))
    return results
