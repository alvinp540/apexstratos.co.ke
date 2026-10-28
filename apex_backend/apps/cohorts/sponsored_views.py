from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin
from apps.accounts.models import User
from apps.notifications.utils import send_notification
from .content_validation import question_set_is_complete
from .models import (
    ParticipationPayment,
    SponsoredViewAssessment,
    SponsoredViewAttempt,
    SponsoredViewDailySettlement,
    SponsoredViewRewardAward,
    SponsoredViewRewardClaim,
    SponsoredViewSettlementAdjustment,
    SponsoredViewPayment,
)
from .weekly_schedule import ASSESSMENT_DURATION_SECONDS, EAT, activity_window, attempt_deadline, next_opening


class SponsoredViewPaymentInputSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(max_length=255)

    def validate_payment_reference(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter the M-Pesa payment reference.')
        return value


class SponsoredViewAdminDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=('verified', 'rejected', 'cancelled', 'refunded'))
    mpesa_transaction_id = serializers.CharField(required=False, allow_blank=True, max_length=255)
    verification_notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    rejection_reason = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    refund_reference = serializers.CharField(required=False, allow_blank=True, max_length=255)


def _assessment_ready(assessment):
    if (
        assessment.field not in dict(SponsoredViewAssessment._meta.get_field('field').choices)
        or assessment.duration_minutes <= 0
        or not isinstance(assessment.learning_objectives, list)
        or len(assessment.learning_objectives) < 3
        or not assessment.description.strip()
        or not assessment.title.strip()
        or (
            assessment.field in {'Medical and Health', 'Law and Society'}
            and not assessment.expert_reviewed
        )
    ):
        return False
    return question_set_is_complete(list(assessment.questions.order_by('order')))


def _attempt_response(attempt):
    now = timezone.now()
    answers = {
        str(question_id): value.get('answer', '') if isinstance(value, dict) else value
        for question_id, value in attempt.answers.items()
    }
    reasoning = {
        str(question_id): value.get('reasoning', '')
        for question_id, value in attempt.answers.items()
        if isinstance(value, dict) and value.get('reasoning')
    }
    questions = []
    for question in attempt.question_snapshot:
        item = {
            key: question[key]
            for key in ('id', 'order', 'prompt', 'options', 'requires_reasoning')
        }
        if attempt.status in {'graded', 'timed_out'}:
            item.update({
                'correct_answer': question['correct_answer'],
                'rationale': question['rationale'],
                'selected_answer': answers.get(question['id']),
                'written_reasoning': reasoning.get(question['id'], ''),
            })
        questions.append(item)
    try:
        cycle_entry = attempt.reward_cycle_entry
    except Exception:
        cycle_entry = None
    reward_cycle = None
    if cycle_entry:
        reward_cycle = {
            'id': str(cycle_entry.cycle_id),
            'cycle_number': cycle_entry.cycle.cycle_number,
            'status': cycle_entry.cycle.status,
            'eligible_completion_count': cycle_entry.cycle.eligible_completion_count,
            'target_completion_count': cycle_entry.cycle.target_completion_count,
            'rank': cycle_entry.rank,
            'winner': cycle_entry.cycle.winner_id == attempt.user_id,
        }
    return {
        'id': str(attempt.id),
        'payment_id': str(attempt.payment_id),
        'assessment_id': str(attempt.assessment_id),
        'title': attempt.assessment.title,
        'field': attempt.assessment.field,
        'questions': questions,
        'answers': answers,
        'reasoning': reasoning,
        'score': attempt.score,
        'status': attempt.status,
        'started_at': attempt.started_at,
        'deadline_at': attempt.deadline_at,
        'server_time': now,
        'time_remaining': max(0, int((attempt.deadline_at - now).total_seconds())),
        'submitted_at': attempt.submitted_at,
        'reward_cycle': reward_cycle,
    }


def _current_reward_cycle_summary(assessment):
    from .models import SponsoredViewRewardCycle
    cycle = SponsoredViewRewardCycle.objects.filter(assessment=assessment).order_by('-cycle_number').first()
    if not cycle:
        return {
            'cycle_number': 1,
            'status': 'open',
            'eligible_completion_count': 0,
            'target_completion_count': 10,
        }
    return {
        'id': str(cycle.id),
        'cycle_number': cycle.cycle_number,
        'status': cycle.status,
        'eligible_completion_count': cycle.eligible_completion_count,
        'target_completion_count': cycle.target_completion_count,
    }


def _finalize_sponsored_view_timeout(attempt, completed_at):
    if attempt.status != 'in_progress':
        return attempt
    questions = {question['id']: question for question in attempt.question_snapshot}
    score = 0
    for question_id, value in attempt.answers.items():
        answer = value.get('answer', '') if isinstance(value, dict) else value
        question = questions.get(str(question_id))
        if question and answer == question['correct_answer']:
            score += 10
    attempt.score = round(score, 2)
    attempt.status = 'timed_out'
    attempt.submitted_at = completed_at
    attempt.save(update_fields=('score', 'status', 'submitted_at'))
    from .reward_cycles import record_sponsored_view_completion
    record_sponsored_view_completion(attempt.id)
    from .support_views import sync_support_eligibilities_for_user
    sync_support_eligibilities_for_user(attempt.user)
    return attempt


class SponsoredViewAssessmentListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        field = request.query_params.get('field')
        week = request.query_params.get('week')
        topic = serializers.CharField(max_length=120, allow_blank=True).run_validation(
            request.query_params.get('topic', ''),
        ).strip()
        assessments = SponsoredViewAssessment.objects.filter(status='published').prefetch_related(
            'questions',
            'payments',
        ).order_by('week', 'field', 'slot')
        if field:
            if field not in dict(SponsoredViewAssessment._meta.get_field('field').choices):
                raise serializers.ValidationError({'field': 'Choose an official study area.'})
            assessments = assessments.filter(field=field)
        if week:
            try:
                week_number = int(week)
            except (TypeError, ValueError) as error:
                raise serializers.ValidationError({'week': 'Week must be from 1 through 8.'}) from error
            if not 1 <= week_number <= 8:
                raise serializers.ValidationError({'week': 'Week must be from 1 through 8.'})
            assessments = assessments.filter(week=week_number)
        if topic:
            assessments = assessments.filter(Q(title__icontains=topic) | Q(description__icontains=topic))

        now = timezone.now()
        window = activity_window('sponsored_view', now)
        active_counts = dict(
            SponsoredViewPayment.objects.filter(
                user=request.user,
                status__in=('pending', 'verified'),
            ).filter(
                Q(attempt__isnull=True) | Q(attempt__status='in_progress', attempt__deadline_at__gt=now),
            ).values('assessment__field').annotate(total=Count('id')).values_list('assessment__field', 'total')
        )
        payments_by_assessment = {}
        for payment in SponsoredViewPayment.objects.filter(
            user=request.user,
            assessment__in=assessments,
        ).select_related('assessment').prefetch_related('attempt').order_by('-requested_at'):
            payments_by_assessment.setdefault(payment.assessment_id, []).append(payment)
        results = []
        for assessment in assessments:
            if not _assessment_ready(assessment):
                continue
            assessment_payments = payments_by_assessment.get(assessment.id, [])
            payment = assessment_payments[0] if assessment_payments else None
            verified_payment = next(
                (item for item in assessment_payments if item.status == 'verified'),
                None,
            )
            attempt_payment = verified_payment or payment
            attempt = getattr(attempt_payment, 'attempt', None) if attempt_payment else None
            results.append({
                'id': str(assessment.id),
                'title': assessment.title,
                'description': assessment.description,
                'field': assessment.field,
                'week': assessment.week,
                'slot': assessment.slot,
                'question_count': 10,
                'duration_minutes': assessment.duration_minutes,
                'access_price_kes': 20,
                'active_entries_for_capability': active_counts.get(assessment.field, 0),
                'active_entry_limit': 5,
                'has_verified_access': bool(verified_payment),
                'can_start': bool(window and verified_payment),
                'reward_cycle': _current_reward_cycle_summary(assessment),
                'window_closes_at': window[1] if window else None,
                'next_opening_at': None if window else next_opening('sponsored_view', now),
                'payment_status': payment.status if payment else None,
                'attempt': _attempt_response(attempt) if attempt else None,
            })
        return Response({'count': len(results), 'results': results})


class SponsoredViewPaymentListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        payments = SponsoredViewPayment.objects.filter(user=request.user).select_related('assessment').prefetch_related('attempt')
        return Response([
            {
                'id': str(payment.id),
                'assessment_id': str(payment.assessment_id),
                'assessment_title': payment.assessment.title,
                'field': payment.assessment.field,
                'amount_kes': payment.amount_kes,
                'till_number': payment.till_number,
                'payment_reference': payment.payment_reference,
                'status': payment.status,
                'rejection_reason': payment.rejection_reason,
                'requested_at': payment.requested_at,
                'verified_at': payment.verified_at,
                'attempt': _attempt_response(payment.attempt) if hasattr(payment, 'attempt') else None,
            }
            for payment in payments
        ])


class SponsoredViewPaymentCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, assessment_id):
        serializer = SponsoredViewPaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assessment = get_object_or_404(
            SponsoredViewAssessment,
            id=assessment_id,
            status='published',
        )
        now = timezone.now()
        window = activity_window('sponsored_view', now)
        if not window:
            return Response(
                {'error': 'Sponsored View payment and attempts are available Monday through Thursday in EAT.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not _assessment_ready(assessment):
            return Response(
                {'error': 'This assessment is not published with ten valid questions and explanations.'},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            User.objects.select_for_update().get(id=request.user.id)
            duplicate_active_entry = SponsoredViewPayment.objects.filter(
                user=request.user,
                assessment=assessment,
                status__in=('pending', 'verified'),
            ).filter(
                Q(attempt__isnull=True) | Q(attempt__status='in_progress', attempt__deadline_at__gt=now),
            ).exists()
            if duplicate_active_entry:
                return Response(
                    {'error': 'You already have an active entry for this assessment.'},
                    status=status.HTTP_409_CONFLICT,
                )
            active_entries = SponsoredViewPayment.objects.filter(
                user=request.user,
                assessment__field=assessment.field,
                status__in=('pending', 'verified'),
            ).filter(
                Q(attempt__isnull=True) | Q(attempt__status='in_progress'),
            ).count()
            if active_entries >= 5:
                return Response(
                    {'error': f'You have reached the maximum of five active entries for {assessment.field}. You can continue participating in other capabilities.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if (
                SponsoredViewPayment.objects.filter(
                    payment_reference=serializer.validated_data['payment_reference'],
                ).exists()
                or ParticipationPayment.objects.filter(
                    payment_reference=serializer.validated_data['payment_reference'],
                ).exists()
            ):
                return Response(
                    {'payment_reference': 'This payment reference is already recorded.'},
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                payment = SponsoredViewPayment.objects.create(
                    user=request.user,
                    assessment=assessment,
                    amount_kes=20,
                    till_number=SponsoredViewPayment.PAYMENT_TILL_NUMBER,
                    payment_reference=serializer.validated_data['payment_reference'],
                )
            except IntegrityError:
                return Response(
                    {'payment_reference': 'This payment reference is already recorded.'},
                    status=status.HTTP_409_CONFLICT,
                )
        return Response({
            'id': str(payment.id),
            'assessment_id': str(assessment.id),
            'assessment_title': assessment.title,
            'amount_kes': payment.amount_kes,
            'till_number': payment.till_number,
            'payment_reference': payment.payment_reference,
            'status': payment.status,
            'message': 'Access is granted as soon as an administrator verifies the KSh 20 payment.',
        }, status=status.HTTP_201_CREATED)


class SponsoredViewPaymentAdminListView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        payments = SponsoredViewPayment.objects.select_related(
            'user', 'assessment', 'verified_by',
        ).order_by('status', 'requested_at')
        return Response([
            {
                'id': str(payment.id),
                'student_id': str(payment.user_id),
                'student_name': payment.user.get_full_name() or payment.user.username,
                'student_email': payment.user.email,
                'assessment_id': str(payment.assessment_id),
                'assessment_title': payment.assessment.title,
                'field': payment.assessment.field,
                'amount_kes': payment.amount_kes,
                'till_number': payment.till_number,
                'payment_reference': payment.payment_reference,
                'mpesa_transaction_id': payment.mpesa_transaction_id,
                'status': payment.status,
                'verification_notes': payment.verification_notes,
                'rejection_reason': payment.rejection_reason,
                'requested_at': payment.requested_at,
                'verified_at': payment.verified_at,
            }
            for payment in payments
        ])


class SponsoredViewPaymentDecisionView(APIView):
    permission_classes = (IsAdmin,)

    def post(self, request, payment_id):
        serializer = SponsoredViewAdminDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        next_status = data['status']
        with transaction.atomic():
            payment_user_id = get_object_or_404(
                SponsoredViewPayment.objects.only('user_id'),
                id=payment_id,
            ).user_id
            User.objects.select_for_update().get(id=payment_user_id)
            payment = get_object_or_404(
                SponsoredViewPayment.objects.select_for_update().select_related('user', 'assessment'),
                id=payment_id,
            )
            is_refund = next_status == 'refunded'
            if (is_refund and payment.status != 'verified') or (not is_refund and payment.status != 'pending'):
                return Response(
                    {'status': 'Refund only a verified payment; other decisions apply only to pending payments.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if next_status in {'rejected', 'cancelled', 'refunded'} and not data.get('rejection_reason', '').strip():
                return Response(
                    {'rejection_reason': 'Provide a reason for this payment decision.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            refund_reference = data.get('refund_reference', '').strip()
            if is_refund and not refund_reference:
                return Response(
                    {'refund_reference': 'Enter the confirmed M-Pesa refund reference.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if is_refund and SponsoredViewSettlementAdjustment.objects.filter(
                refund_reference=refund_reference,
            ).exists():
                return Response(
                    {'refund_reference': 'This refund reference is already recorded.'},
                    status=status.HTTP_409_CONFLICT,
                )
            transaction_id = data.get('mpesa_transaction_id', '').strip()
            if next_status == 'verified' and not transaction_id:
                return Response(
                    {'mpesa_transaction_id': 'Enter the confirmed M-Pesa transaction ID.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if next_status == 'verified' and (
                payment.amount_kes != 20
                or payment.till_number != SponsoredViewPayment.PAYMENT_TILL_NUMBER
            ):
                return Response(
                    {'error': 'Confirm a KES 20 payment to company M-Pesa Till 1598106 before verifying access.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if next_status == 'verified' and (
                ParticipationPayment.objects.filter(mpesa_transaction_id=transaction_id).exists()
                or SponsoredViewPayment.objects.exclude(id=payment.id).filter(
                    mpesa_transaction_id=transaction_id,
                ).exists()
            ):
                return Response(
                    {'mpesa_transaction_id': 'This M-Pesa transaction is already linked to another payment.'},
                    status=status.HTTP_409_CONFLICT,
                )
            payment.status = next_status
            if next_status == 'verified':
                payment.mpesa_transaction_id = transaction_id
            payment.verification_notes = data.get('verification_notes', '').strip()
            payment.rejection_reason = data.get('rejection_reason', '').strip()
            if next_status == 'verified':
                payment.verified_by = request.user
                payment.verified_at = timezone.now()
            payment.save(update_fields=(
                'status', 'mpesa_transaction_id', 'verification_notes', 'rejection_reason',
                'verified_by', 'verified_at',
            ))
            if is_refund:
                award = SponsoredViewRewardAward.objects.select_for_update().filter(payment=payment).first()
                claim = SponsoredViewRewardClaim.objects.select_for_update().filter(award=award).first() if award else None
                try:
                    cycle_entry = payment.reward_cycle_entry
                except Exception:
                    cycle_entry = None
                cycle = cycle_entry.cycle if cycle_entry else None
                counted_in_settlement = False
                settlement = award.settlement if award else None
                if cycle and cycle.status in {'finalized', 'exception'}:
                    settlement = getattr(cycle, 'settlement_record', None)
                elif payment.verified_at:
                    settlement_day = payment.verified_at.astimezone(EAT).date()
                    settlement = SponsoredViewDailySettlement.objects.filter(
                        assessment=payment.assessment,
                        settlement_date=settlement_day,
                        status='finalized',
                        reward_cycle__isnull=True,
                    ).first()
                if cycle and cycle.status not in {'finalized', 'exception'}:
                    cycle_entry.status = 'refunded'
                    cycle_entry.save(update_fields=('status',))
                    cycle.eligible_completion_count = cycle.entries.filter(status='eligible').count()
                    if cycle.status in {'full', 'failed'}:
                        cycle.status = 'open'
                        cycle.full_at = None
                        cycle.save(update_fields=('eligible_completion_count', 'status', 'full_at'))
                    else:
                        cycle.save(update_fields=('eligible_completion_count',))
                    settlement = None
                elif cycle:
                    cycle_entry.status = 'refunded'
                    cycle_entry.save(update_fields=('status',))
                else:
                    attempt = SponsoredViewAttempt.objects.filter(
                        payment=payment,
                        status__in=('graded', 'timed_out'),
                        is_flagged=False,
                        submitted_at__gte=settlement.period_start if settlement else timezone.now(),
                        submitted_at__lt=settlement.period_end if settlement else timezone.now(),
                    ).first()
                    if not award:
                        settlement = None
                    counted_in_settlement = bool(settlement and attempt and attempt.submitted_at)
                if cycle and cycle.status in {'finalized', 'exception'}:
                    counted_in_settlement = bool(settlement)
                payout_recovery_required = bool(claim and claim.status == 'paid')
                try:
                    with transaction.atomic():
                        SponsoredViewSettlementAdjustment.objects.create(
                            settlement=settlement,
                            reward_cycle=cycle,
                            payment=payment,
                            actor=request.user,
                            refunded_amount_kes=payment.amount_kes,
                            refund_reference=refund_reference,
                            revenue_reversal_kes=payment.amount_kes if counted_in_settlement else 0,
                            platform_share_reversal_kes=payment.amount_kes // 2 if counted_in_settlement else 0,
                            rewards_share_reversal_kes=payment.amount_kes - payment.amount_kes // 2 if counted_in_settlement else 0,
                            award_reversal_kes=award.amount_kes if award and award.status == 'awarded' else 0,
                            payout_recovery_required=payout_recovery_required,
                            reason=payment.rejection_reason,
                        )
                except IntegrityError as error:
                    raise serializers.ValidationError({
                        'refund_reference': 'This refund reference or payment refund is already recorded.',
                    }) from error
                if award and award.status == 'awarded':
                    award.status = 'reversed'
                    award.reversal_reason = payment.rejection_reason
                    award.reversed_by = request.user
                    award.reversed_at = timezone.now()
                    award.save(update_fields=('status', 'reversal_reason', 'reversed_by', 'reversed_at'))
                    if claim:
                        claim.status = 'reversed'
                        claim.rejection_reason = payment.rejection_reason
                        claim.save(update_fields=('status', 'rejection_reason', 'updated_at'))
                    if cycle:
                        cycle.payout_status = (
                            'recovery_required' if payout_recovery_required else 'reversed'
                        )
                        cycle.save(update_fields=('payout_status',))
            title = 'Sponsored View payment verified' if next_status == 'verified' else f'Sponsored View payment {next_status}'
            message = (
                f'Your KSh 20 payment for {payment.assessment.title} is verified. '
                'You can start the assessment during its Monday–Thursday EAT window.'
                if next_status == 'verified'
                else f'Your Sponsored View payment was rejected. {payment.rejection_reason}'
            )
            send_notification(
                user=payment.user,
                notification_type='payment',
                title=title,
                message=message,
                action_url='/learning',
                metadata={'payment_id': str(payment.id), 'status': next_status, 'library': 'sponsored_view'},
            )
        return Response({
            'id': str(payment.id),
            'status': payment.status,
            'mpesa_transaction_id': payment.mpesa_transaction_id,
            'verified_at': payment.verified_at,
        })


class StartSponsoredViewAttemptView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, payment_id):
        with transaction.atomic():
            payment = get_object_or_404(
                SponsoredViewPayment.objects.select_for_update().select_related('assessment').prefetch_related('assessment__questions'),
                id=payment_id,
                user=request.user,
            )
            assessment = payment.assessment
            now = timezone.now()
            attempt = SponsoredViewAttempt.objects.select_for_update().filter(payment=payment).first()
            if attempt:
                if attempt.status == 'in_progress' and now >= attempt.deadline_at:
                    _finalize_sponsored_view_timeout(attempt, now)
                return Response(_attempt_response(attempt))
            window = activity_window('sponsored_view', now)
            if window is None:
                return Response(
                    {'error': 'Sponsored View assessments are available Monday through Thursday in EAT.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if payment.status != 'verified':
                return Response(
                    {'error': 'A verified KSh 20 payment is required before starting this assessment.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if assessment.status != 'published' or not _assessment_ready(assessment):
                return Response(
                    {'error': 'This assessment is not available with a complete, published question set.'},
                    status=status.HTTP_409_CONFLICT,
                )
            questions = list(assessment.questions.order_by('order'))
            started_at = now
            attempt = SponsoredViewAttempt.objects.create(
                payment=payment,
                user=request.user,
                assessment=assessment,
                question_snapshot=[
                    {
                        'id': str(question.id),
                        'order': question.order,
                        'prompt': question.prompt,
                        'options': question.options,
                        'correct_answer': question.correct_answer,
                        'rationale': question.rationale,
                        'requires_reasoning': question.requires_reasoning,
                    }
                    for question in questions
                ],
                started_at=started_at,
                deadline_at=attempt_deadline(
                    'sponsored_view',
                    started_at,
                    ASSESSMENT_DURATION_SECONDS,
                ),
            )
        return Response(_attempt_response(attempt), status=status.HTTP_201_CREATED)


class SaveSponsoredViewAttemptAnswersView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, attempt_id):
        with transaction.atomic():
            attempt = get_object_or_404(
                SponsoredViewAttempt.objects.select_for_update(),
                id=attempt_id,
                user=request.user,
            )
            if attempt.status != 'in_progress':
                return Response({'error': 'This assessment attempt is no longer active.'}, status=status.HTTP_409_CONFLICT)
            now = timezone.now()
            if now >= attempt.deadline_at:
                _finalize_sponsored_view_timeout(attempt, now)
                return Response(_attempt_response(attempt))
            answers = request.data.get('answers', {})
            reasoning = request.data.get('reasoning', {})
            if not isinstance(answers, dict) or not isinstance(reasoning, dict):
                raise serializers.ValidationError('Answers and reasoning must be maps keyed by question ID.')
            question_map = {question['id']: question for question in attempt.question_snapshot}
            normalized = dict(attempt.answers)
            for question_id, answer in answers.items():
                question_id = str(question_id)
                if question_id not in question_map or answer not in question_map[question_id]['options']:
                    raise serializers.ValidationError({'answers': 'One or more answer choices are invalid.'})
                existing = normalized.get(question_id, {})
                normalized[question_id] = {
                    'answer': answer,
                    'reasoning': existing.get('reasoning', '') if isinstance(existing, dict) else '',
                }
            for question_id, text in reasoning.items():
                question_id = str(question_id)
                if question_id not in question_map or not isinstance(text, str) or len(text) > 5000:
                    raise serializers.ValidationError({'reasoning': 'One or more written responses are invalid.'})
                existing = normalized.get(question_id, {})
                normalized[question_id] = {
                    'answer': existing.get('answer', '') if isinstance(existing, dict) else existing,
                    'reasoning': text,
                }
            attempt.answers = normalized
            attempt.save(update_fields=('answers',))
        return Response(_attempt_response(attempt))


class SubmitSponsoredViewAttemptView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, attempt_id):
        with transaction.atomic():
            attempt = get_object_or_404(
                SponsoredViewAttempt.objects.select_for_update(),
                id=attempt_id,
                user=request.user,
            )
            if attempt.status in {'graded', 'timed_out'}:
                from .support_views import sync_support_eligibilities_for_user
                sync_support_eligibilities_for_user(attempt.user)
                from .reward_cycles import record_sponsored_view_completion
                record_sponsored_view_completion(attempt.id)
                return Response(_attempt_response(attempt))
            if attempt.status != 'in_progress':
                return Response({'error': 'This assessment attempt is no longer active.'}, status=status.HTTP_409_CONFLICT)
            now = timezone.now()
            if now >= attempt.deadline_at:
                _finalize_sponsored_view_timeout(attempt, now)
                return Response(_attempt_response(attempt))
            answers = request.data.get('answers', {})
            reasoning = request.data.get('reasoning', {})
            if not isinstance(answers, dict) or not isinstance(reasoning, dict):
                raise serializers.ValidationError('Answers and reasoning must be maps keyed by question ID.')
            questions = {
                question['id']: question
                for question in attempt.question_snapshot
            }
            if set(map(str, answers)) != set(questions):
                raise serializers.ValidationError({'answers': 'Answer every question exactly once.'})
            if any(
                answer not in questions[str(question_id)]['options']
                for question_id, answer in answers.items()
            ):
                raise serializers.ValidationError({'answers': 'One or more answer choices are invalid.'})
            normalized_reasoning = {str(key): value for key, value in reasoning.items()}
            for question in questions.values():
                question_id = question['id']
                text = normalized_reasoning.get(question_id, '')
                if question.get('requires_reasoning') and (not isinstance(text, str) or not text.strip()):
                    raise serializers.ValidationError({'reasoning': 'Provide the required written reasoning.'})
                if not isinstance(text, str) or len(text) > 5000:
                    raise serializers.ValidationError({'reasoning': 'Written reasoning must be at most 5000 characters.'})
            attempt.answers = {
                str(question_id): {
                    'answer': answer,
                    'reasoning': normalized_reasoning.get(str(question_id), ''),
                }
                for question_id, answer in answers.items()
            }
            attempt.score = round(
                sum(
                    10
                    for question in questions.values()
                    if answers.get(question['id']) == question['correct_answer']
                ),
                2,
            )
            attempt.status = 'graded'
            attempt.submitted_at = now
            attempt.save(update_fields=('answers', 'score', 'status', 'submitted_at'))
            from .reward_cycles import record_sponsored_view_completion
            record_sponsored_view_completion(attempt.id)
            from .support_views import sync_support_eligibilities_for_user
            sync_support_eligibilities_for_user(attempt.user)
        return Response(_attempt_response(attempt))
