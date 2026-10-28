from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Max

from apps.profiles.models import Mentor
from .models import (
    AssessmentAttempt,
    Cohort,
    CohortCoachAssignment,
    CohortWalletEntry,
    PSPRegistration,
)


def get_reward_plan(participant_count):
    """Return the coach counts and marketing budget for a cohort size."""
    if participant_count >= 100:
        return {'skills': 6, 'consistency': 4, 'improvement': 2, 'marketing': Decimal('1000'), 'skills_payout': Decimal('500'), 'consistency_payout': Decimal('300'), 'improvement_payout': Decimal('300')}
    if participant_count >= 50:
        return {'skills': 3, 'consistency': 2, 'improvement': 1, 'marketing': Decimal('500'), 'skills_payout': Decimal('500'), 'consistency_payout': Decimal('300'), 'improvement_payout': Decimal('300')}
    if participant_count >= 20:
        return {'skills': 1, 'consistency': 1, 'improvement': 1, 'marketing': Decimal('300'), 'skills_payout': Decimal('500'), 'consistency_payout': Decimal('300'), 'improvement_payout': Decimal('300')}
    raise ValueError('At least 20 active participants are required before rewards can be allocated.')


def get_tier_amount(payment_tier):
    return {'10kes': Decimal('10'), '100kes': Decimal('100'), '1000kes': Decimal('1000')}[payment_tier]


@transaction.atomic
def allocate_cohort_rewards(cohort_id):
    cohort = Cohort.objects.select_for_update().get(id=cohort_id)
    if CohortWalletEntry.objects.filter(cohort=cohort).exists():
        raise ValueError('Rewards have already been allocated for this cohort.')

    participant_ids = list(
        PSPRegistration.objects.filter(
            cohort=cohort,
            status='active',
        ).values_list('user_id', flat=True).distinct()
    )
    if len(participant_ids) < cohort.assessment_unlock_threshold:
        raise ValueError('The cohort has not reached its configured reward threshold.')

    performance = list(
        AssessmentAttempt.objects.filter(
            cohort=cohort,
            user_id__in=participant_ids,
            status__in=('graded', 'timed_out'),
            score__isnull=False,
            is_flagged=False,
        ).values('user_id').annotate(score=Avg('score'), latest=Max('submitted_at')).order_by('-score', 'latest')
    )
    if not performance:
        raise ValueError('No eligible graded assessment results are available.')

    participant_count = len(participant_ids)
    reward_plan = get_reward_plan(participant_count)
    skills_count = reward_plan['skills']
    consistency_count = reward_plan['consistency']
    improvement_count = reward_plan['improvement']

    selected = []
    for row in performance[:skills_count]:
        selected.append(('skills', row))
    for row in performance[skills_count:skills_count + consistency_count]:
        selected.append(('consistency', row))
    for row in performance[skills_count + consistency_count:skills_count + consistency_count + improvement_count]:
        selected.append(('improvement', row))

    tier_amount = get_tier_amount(cohort.payment_tier)
    payout_by_role = {
        'skills': tier_amount,
        'consistency': tier_amount,
        'improvement': tier_amount,
    }
    thresholds = {'skills': 70, 'consistency': 70, 'improvement': 5}
    for role, row in selected:
        user = cohort.enrollments.get(user_id=row['user_id']).user
        attempts = list(AssessmentAttempt.objects.filter(cohort=cohort, user=user, status__in=('graded', 'timed_out'), score__isnull=False).order_by('submitted_at').values_list('score', flat=True))
        baseline = float(attempts[0]) if attempts else 0
        latest = float(attempts[-1]) if attempts else float(row['score'])
        consistency = (min(attempts) / max(attempts) * 100) if attempts and max(attempts) else 0
        improvement_delta = latest - baseline
        metric = float(row['score']) if role == 'skills' else consistency if role == 'consistency' else improvement_delta
        valid = metric >= thresholds[role] if role != 'improvement' else len(attempts) > 1 and metric >= thresholds[role]
        reason = f'{role.title()} metric {metric:.2f}; threshold {thresholds[role]:.2f}.'
        CohortCoachAssignment.objects.create(
            cohort=cohort,
            user=user,
            role=role,
            score=Decimal(str(round(row['score'], 2))),
            payout_amount=payout_by_role[role] if valid else Decimal('0'),
            eligibility_status='valid' if valid else 'invalid',
            eligibility_reason=reason,
            improvement_delta=Decimal(str(round(improvement_delta, 2))),
        )
        if valid:
            Mentor.objects.get_or_create(user=user, defaults={'tier': 'cohort-coach'})
            CohortWalletEntry.objects.create(cohort=cohort, wallet='mentor_payout', user=user, amount=payout_by_role[role], description=f'{role.title()} coach payout')
            from apps.notifications.utils import send_notification
            send_notification(user=user, notification_type='payment', title='Mentorship payout approved', message=f'Your {role} mentorship payout for {cohort.title} is valid. Guide participants through your track, record their follow-up progress, and share how Apex supports capability growth.', action_url='/coach-payouts', metadata={'cohort_id': str(cohort.id), 'coach_role': role, 'amount': str(payout_by_role[role]), 'eligibility_status': 'valid'})

    total_received = sum(
        PSPRegistration.objects.filter(cohort=cohort, status='active').values_list('amount_expected', flat=True),
        Decimal('0'),
    )
    mentor_total = sum((payout_by_role[role] for role, row in selected if CohortCoachAssignment.objects.filter(cohort=cohort, user_id=row['user_id'], role=role, eligibility_status='valid').exists()), Decimal('0'))
    marketing = tier_amount * Decimal(str(participant_count)) / Decimal('10')
    admin_remainder = total_received - mentor_total - marketing
    if admin_remainder < 0:
        raise ValueError('Configured payouts exceed verified cohort receipts.')

    CohortWalletEntry.objects.create(
        cohort=cohort,
        wallet='account_based_marketing',
        amount=marketing,
        description=f'Account-based marketing wallet; Till {PSPRegistration.PAYMENT_TILL_NUMBER}',
    )
    CohortWalletEntry.objects.create(
        cohort=cohort,
        wallet='admin',
        amount=admin_remainder,
        description='Remaining verified cohort receipts allocated to admin wallet',
    )
    return {
        'participants': len(participant_ids),
        'coaches': len(selected),
        'coach_counts': {
            'skills': skills_count,
            'consistency': consistency_count,
            'improvement': improvement_count,
        },
        'coach_payouts': {
            'skills': payout_by_role['skills'],
            'consistency': payout_by_role['consistency'],
            'improvement': payout_by_role['improvement'],
        },
        'payment_tier': cohort.payment_tier,
        'tier_amount': tier_amount,
        'total_received': total_received,
        'mentor_total': mentor_total,
        'marketing': marketing,
        'apex_wallet': admin_remainder,
        'admin_remainder': admin_remainder,
    }
