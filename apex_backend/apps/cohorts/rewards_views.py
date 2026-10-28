from datetime import date, timedelta, datetime
import re

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin
from apps.notifications.utils import send_notification
from .models import (
    SponsoredViewAttempt,
    SponsoredViewDailySettlement,
    SponsoredViewRewardClaim,
    SponsoredViewSettlementAdjustment,
)
from .reward_settlement import settle_daily_sponsored_view
from .weekly_schedule import EAT


class RewardClaimSubmissionSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=('mpesa',))
    consent = serializers.BooleanField()


def _claim_payload(claim):
    phone = (claim.user.phone_number or '').strip()
    masked_phone = f'••••{phone[-3:]}' if len(phone) >= 3 else ''
    award = claim.award
    return {
        'id': str(claim.id),
        'award_id': str(award.id),
        'amount_kes': award.amount_kes,
        'tutorial': award.settlement.assessment.title,
        'capability': award.settlement.capability,
        'settlement_date': award.settlement.settlement_date,
        'selection': award.selection,
        'score': award.score,
        'rank': award.rank,
        'status': claim.status,
        'payment_method': claim.payment_method,
        'masked_destination': masked_phone,
        'payout_reference': claim.payout_reference,
        'rejection_reason': claim.rejection_reason,
        'created_at': claim.created_at,
        'submitted_at': claim.submitted_at,
        'merit_confirmed_at': claim.merit_confirmed_at,
        'payout_confirmed_at': claim.payout_confirmed_at,
    }


class MyRewardClaimsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        claims = SponsoredViewRewardClaim.objects.filter(user=request.user).select_related(
            'user', 'merit_confirmed_by', 'award__settlement__assessment',
        ).order_by('-created_at')
        return Response([_claim_payload(claim) for claim in claims])


class SubmitRewardClaimView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, claim_id):
        serializer = RewardClaimSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data['consent']:
            raise serializers.ValidationError({'consent': 'Confirm the payout details before submitting.'})
        phone = re.sub(r'[\s-]', '', request.user.phone_number or '')
        if not re.fullmatch(r'(?:\+?254|0)\d{9}', phone):
            raise serializers.ValidationError({'phone_number': 'Add a valid Kenyan phone number to your account before claiming.'})
        with transaction.atomic():
            claim = get_object_or_404(
                SponsoredViewRewardClaim.objects.select_for_update().select_related(
                    'user', 'award__settlement__assessment',
                ),
                id=claim_id,
                user=request.user,
            )
            if claim.status != 'claim_required':
                return Response({'status': 'This reward claim has already been submitted or reviewed.'}, status=status.HTTP_409_CONFLICT)
            claim.payment_method = serializer.validated_data['payment_method']
            claim.status = 'claim_submitted'
            claim.consented_at = timezone.now()
            claim.submitted_at = timezone.now()
            claim.save(update_fields=('payment_method', 'status', 'consented_at', 'submitted_at', 'updated_at'))
        return Response(_claim_payload(claim), status=status.HTTP_200_OK)


class AdminRewardSettlementsView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        rows = SponsoredViewDailySettlement.objects.select_related('assessment').prefetch_related(
            'adjustments__payment',
        ).order_by('-settlement_date', 'capability')[:200]
        results = []
        for row in rows:
            adjustments = list(row.adjustments.all())
            revenue_reversal = sum(item.revenue_reversal_kes for item in adjustments)
            platform_reversal = sum(item.platform_share_reversal_kes for item in adjustments)
            rewards_reversal = sum(item.rewards_share_reversal_kes for item in adjustments)
            results.append({
                'id': str(row.id), 'assessment_id': str(row.assessment_id),
                'tutorial': row.assessment.title, 'capability': row.capability,
                'settlement_date': row.settlement_date, 'eligible_participant_count': row.eligible_participant_count,
                'total_revenue_kes': row.total_revenue_kes, 'platform_share_kes': row.platform_share_kes,
                'rewards_budget_kes': row.rewards_budget_kes, 'primary_winner_count': row.primary_winner_count,
                'secondary_winner_count': row.secondary_winner_count, 'awarded_total_kes': row.awarded_total_kes,
                'unallocated_reserve_kes': row.unallocated_reserve_kes, 'criteria_snapshot': row.criteria_snapshot,
                'status': row.status, 'attempt_count': row.attempt_count, 'error_message': row.error_message,
                'revenue_reversal_kes': revenue_reversal,
                'adjusted_revenue_kes': row.total_revenue_kes - revenue_reversal,
                'platform_share_reversal_kes': platform_reversal,
                'rewards_share_reversal_kes': rewards_reversal,
                'payout_recovery_required_count': sum(1 for item in adjustments if item.payout_recovery_required),
                'adjustments': [{
                    'id': str(item.id),
                    'payment_reference': item.payment.payment_reference,
                    'refund_reference': item.refund_reference,
                    'refunded_amount_kes': item.refunded_amount_kes,
                    'revenue_reversal_kes': item.revenue_reversal_kes,
                    'platform_share_reversal_kes': item.platform_share_reversal_kes,
                    'rewards_share_reversal_kes': item.rewards_share_reversal_kes,
                    'award_reversal_kes': item.award_reversal_kes,
                    'payout_recovery_required': item.payout_recovery_required,
                    'reason': item.reason,
                    'created_at': item.created_at,
                } for item in adjustments],
                'idempotency_key': row.idempotency_key,
            })
        unassigned_adjustments = SponsoredViewSettlementAdjustment.objects.filter(
            settlement__isnull=True,
        ).select_related('payment').order_by('-created_at')[:200]
        return Response({
            'results': results,
            'unassigned_adjustments': [{
                'id': str(item.id),
                'payment_reference': item.payment.payment_reference,
                'refund_reference': item.refund_reference,
                'refunded_amount_kes': item.refunded_amount_kes,
                'reason': item.reason,
                'created_at': item.created_at,
            } for item in unassigned_adjustments],
        })

    def post(self, request):
        raw_date = request.data.get('date')
        try:
            settlement_date = date.fromisoformat(raw_date) if raw_date else datetime.now(EAT).date() - timedelta(days=1)
        except (TypeError, ValueError):
            raise serializers.ValidationError({'date': 'Use an ISO date in YYYY-MM-DD format.'})
        result = settle_daily_sponsored_view(settlement_date)
        return Response({
            'date': settlement_date,
            'settlements': [str(row.id) for row, _created in result],
            'created_count': sum(1 for _row, created in result if created),
        })


class AdminRewardClaimsView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        claims = SponsoredViewRewardClaim.objects.select_related(
            'user', 'merit_confirmed_by', 'award__settlement__assessment', 'award__payment',
        ).order_by('status', 'created_at')[:500]
        return Response([{
            **_claim_payload(claim),
            'student_name': claim.user.get_full_name() or claim.user.username,
            'student_email': claim.user.email,
            'destination_phone': claim.user.phone_number,
            'merit_confirmed_by': claim.merit_confirmed_by.get_full_name() or claim.merit_confirmed_by.username if claim.merit_confirmed_by else None,
            'payout_idempotency_key': str(claim.id),
        } for claim in claims])

    def patch(self, request, claim_id):
        action = serializers.ChoiceField(choices=('verify', 'queue_payout', 'reject', 'confirm_paid'))
        action_value = action.run_validation(request.data.get('action'))
        with transaction.atomic():
            claim = get_object_or_404(
                SponsoredViewRewardClaim.objects.select_for_update().select_related(
                    'user', 'award__settlement__assessment',
                ), id=claim_id,
            )
            if action_value == 'verify':
                if claim.status != 'claim_submitted':
                    return Response({'status': 'Only submitted claims can be verified.'}, status=status.HTTP_409_CONFLICT)
                award = claim.award
                if award.status != 'awarded' or award.payment.status != 'verified':
                    return Response({'status': 'The award or its KES 20 payment is no longer eligible.'}, status=status.HTTP_409_CONFLICT)
                try:
                    attempt = award.payment.attempt
                except SponsoredViewAttempt.DoesNotExist:
                    return Response({'status': 'The source assessment attempt is unavailable.'}, status=status.HTTP_409_CONFLICT)
                if (
                    attempt.status != 'graded' or attempt.is_flagged or attempt.score is None
                    or attempt.score != award.score or attempt.user_id != claim.user_id
                    or attempt.assessment_id != award.payment.assessment_id
                ):
                    return Response({'status': 'The stored merit score does not match an eligible graded attempt.'}, status=status.HTTP_409_CONFLICT)
                claim.status = 'verified'
                claim.verified_by = request.user
                claim.verified_at = timezone.now()
                claim.merit_confirmed_by = request.user
                claim.merit_confirmed_at = timezone.now()
            elif action_value == 'queue_payout':
                if claim.status != 'verified' or not claim.merit_confirmed_at:
                    return Response({'status': 'Only claims with a confirmed merit score can be queued for payout.'}, status=status.HTTP_409_CONFLICT)
                if claim.award.status != 'awarded':
                    return Response({'status': 'A reversed award cannot be queued for payout.'}, status=status.HTTP_409_CONFLICT)
                claim.status = 'payout_pending'
            elif action_value == 'reject':
                reason = str(request.data.get('reason', '')).strip()
                if not reason:
                    raise serializers.ValidationError({'reason': 'Provide a reason for rejecting the claim.'})
                if claim.status not in {'claim_submitted', 'payout_pending'}:
                    return Response({'status': 'This claim cannot be rejected in its current state.'}, status=status.HTTP_409_CONFLICT)
                claim.status = 'rejected'
                claim.rejection_reason = reason[:5000]
                claim.verified_by = request.user
                claim.verified_at = timezone.now()
            else:
                reference = str(request.data.get('payout_reference', '')).strip()
                note = str(request.data.get('reconciliation_note', '')).strip()
                if claim.status != 'payout_pending':
                    return Response({'status': 'Only pending payouts can be reconciled.'}, status=status.HTTP_409_CONFLICT)
                if not reference or not note:
                    raise serializers.ValidationError({'payout_reference': 'Provide the confirmed provider reference and reconciliation note.'})
                if SponsoredViewRewardClaim.objects.exclude(id=claim.id).filter(payout_reference=reference).exists():
                    raise serializers.ValidationError({'payout_reference': 'This provider reference is already recorded.'})
                claim.status = 'paid'
                claim.payout_reference = reference[:255]
                claim.payout_reconciliation_note = note[:5000]
                claim.payout_confirmed_by = request.user
                claim.payout_confirmed_at = timezone.now()
            try:
                with transaction.atomic():
                    claim.save()
            except IntegrityError:
                return Response({'payout_reference': 'This provider reference is already recorded.'}, status=status.HTTP_409_CONFLICT)
            if action_value in {'verify', 'queue_payout', 'confirm_paid', 'reject'}:
                send_notification(
                    user=claim.user,
                    notification_type='payment',
                    title='Reward claim status updated',
                    message=f'Your KES {claim.award.amount_kes} reward claim is now {claim.status.replace("_", " ")}.',
                    action_url='/rewards',
                    metadata={'claim_id': str(claim.id), 'status': claim.status},
                )
        return Response(_claim_payload(claim))
