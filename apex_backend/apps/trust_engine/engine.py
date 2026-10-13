"""
APEX Trust & Merit Scoring Engine
Composite score formula:
  overall_merit = (
    0.30 * psp_consistency +
    0.30 * cohort_performance +
    0.25 * vendor_rating +
    0.15 * authenticity_confidence
  )
Tier thresholds: bronze 0-19, silver 20-39, gold 40-59, platinum 60-79, apex 80-100
"""

from django.db.models import Avg
from django.utils import timezone

WEIGHTS = {
    'psp_consistency':    0.30,
    'cohort_performance': 0.30,
    'vendor_rating':      0.25,
    'authenticity':       0.15,
}

TIER_THRESHOLDS = [
    (80, 'apex'),
    (60, 'platinum'),
    (40, 'gold'),
    (20, 'silver'),
    (0,  'bronze'),
]


def calculate_psp_consistency(user) -> float:
    from apps.cohorts.models import AssessmentAttempt

    window_start = timezone.now() - timezone.timedelta(weeks=12)
    submitted_at_values = AssessmentAttempt.objects.filter(
        user=user,
        status='graded',
        is_flagged=False,
        submitted_at__gte=window_start,
    ).values_list('submitted_at', flat=True)
    active_weeks = {
        (submitted_at.isocalendar().year, submitted_at.isocalendar().week)
        for submitted_at in submitted_at_values
        if submitted_at is not None
    }
    return round((len(active_weeks) / 12) * 100, 2)


def calculate_cohort_performance(user) -> float:
    from apps.cohorts.models import AssessmentAttempt
    attempts = AssessmentAttempt.objects.filter(
        user=user, status='graded', score__isnull=False
    )
    if not attempts.exists():
        return 0.0

    recent_cutoff = timezone.now() - timezone.timedelta(days=180)
    total_weighted = 0.0
    total_weight = 0.0

    for attempt in attempts:
        weight = 2.0 if attempt.submitted_at and attempt.submitted_at >= recent_cutoff else 1.0
        total_weighted += (attempt.score or 0) * weight
        total_weight += weight

    return round(total_weighted / total_weight, 2) if total_weight else 0.0


def calculate_vendor_rating(user) -> float:
    from apps.vendor.models import VendorRating
    ratings = VendorRating.objects.filter(professional=user)
    if not ratings.exists():
        return 0.0
    avg = ratings.aggregate(avg=Avg('overall_score'))['avg'] or 0.0
    return round(((avg - 1) / 4) * 100, 2)


def calculate_authenticity_confidence(user) -> float:
    from apps.cohorts.models import AssessmentAttempt
    flagged_count = AssessmentAttempt.objects.filter(user=user, is_flagged=True).count()
    return max(0.0, 100.0 - (flagged_count * 20))


def get_tier(score: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return 'bronze'


def recalculate_trust_score(user, reason: str = 'Manual recalculation'):
    from apps.trust_engine.models import TrustScore, TrustScoreHistory

    psp    = calculate_psp_consistency(user)
    cohort = calculate_cohort_performance(user)
    vendor = calculate_vendor_rating(user)
    auth   = calculate_authenticity_confidence(user)

    overall = round(
        WEIGHTS['psp_consistency']    * psp    +
        WEIGHTS['cohort_performance'] * cohort +
        WEIGHTS['vendor_rating']      * vendor +
        WEIGHTS['authenticity']       * auth,
        2,
    )
    tier = get_tier(overall)

    ts, _ = TrustScore.objects.update_or_create(
        user=user,
        defaults={
            'psp_consistency_score':    psp,
            'cohort_performance_score': cohort,
            'vendor_rating_score':      vendor,
            'authenticity_confidence':  auth,
            'overall_merit_score':      overall,
            'tier':                     tier,
        },
    )

    TrustScoreHistory.objects.create(
        user=user,
        overall_merit_score=overall,
        psp_consistency_score=psp,
        cohort_performance_score=cohort,
        vendor_rating_score=vendor,
        authenticity_confidence=auth,
        reason=reason,
    )

    from apps.rankings.tasks import update_user_ranking
    update_user_ranking.delay(str(user.id))

    return ts
