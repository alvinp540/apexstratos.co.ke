from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
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
    SponsoredViewPayment,
)
from .weekly_schedule import EAT, activity_window, attempt_deadline, next_opening


class SponsoredViewPaymentInputSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(max_length=255)

    def validate_payment_reference(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter the M-Pesa payment reference.')
        return value


class SponsoredViewAdminDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=('verified', 'rejected'))
    mpesa_transaction_id = serializers.CharField(required=False, allow_blank=True, max_length=255)
    verification_notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    rejection_reason = serializers.CharField(required=False, allow_blank=True, max_length=5000)


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
        if attempt.status == 'graded':
            item.update({
                'correct_answer': question['correct_answer'],
                'rationale': question['rationale'],
                'selected_answer': answers.get(question['id']),
                'written_reasoning': reasoning.get(question['id'], ''),
            })
        questions.append(item)
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
    }


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
                'has_verified_access': bool(verified_payment),
                'can_start': bool(window and verified_payment),
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
        local_day = now.astimezone(EAT).date()
        day_start = timezone.make_aware(
            timezone.datetime.combine(local_day, time.min),
            EAT,
        )
        day_end = day_start + timedelta(days=1)
        with transaction.atomic():
            User.objects.select_for_update().get(id=request.user.id)
            payments_today = SponsoredViewPayment.objects.select_for_update().filter(
                user=request.user,
                requested_at__gte=day_start,
                requested_at__lt=day_end,
                status__in=('pending', 'verified'),
            ).count()
            if payments_today >= 5:
                return Response(
                    {'error': 'The limit is five paid Sponsored View attempts per student per EAT calendar day.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
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
            if payment.status != 'pending':
                return Response(
                    {'status': 'Only pending Sponsored View payments can be reviewed.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if next_status == 'rejected' and not data.get('rejection_reason', '').strip():
                return Response(
                    {'rejection_reason': 'Provide a reason for rejecting this payment.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            transaction_id = data.get('mpesa_transaction_id', '').strip()
            if next_status == 'verified' and not transaction_id:
                return Response(
                    {'mpesa_transaction_id': 'Enter the confirmed M-Pesa transaction ID.'},
                    status=status.HTTP_400_BAD_REQUEST,
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
            local_day = payment.requested_at.astimezone(EAT).date()
            day_start = timezone.make_aware(datetime.combine(local_day, time.min), EAT)
            day_end = day_start + timedelta(days=1)
            verified_today = SponsoredViewPayment.objects.filter(
                user=payment.user,
                requested_at__gte=day_start,
                requested_at__lt=day_end,
                status='verified',
            ).count()
            if next_status == 'verified' and verified_today >= 5:
                return Response(
                    {'status': 'The student has already reached five verified attempts for that EAT day.'},
                    status=status.HTTP_409_CONFLICT,
                )
            payment.status = next_status
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
            title = 'Sponsored View payment verified' if next_status == 'verified' else 'Sponsored View payment not verified'
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
            attempt = SponsoredViewAttempt.objects.filter(payment=payment).first()
            if attempt:
                if attempt.status == 'in_progress' and now >= attempt.deadline_at:
                    attempt.status = 'timed_out'
                    attempt.submitted_at = now
                    attempt.save(update_fields=('status', 'submitted_at'))
                    return Response({'error': 'The assessment deadline has expired.'}, status=status.HTTP_410_GONE)
                return Response(_attempt_response(attempt))
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
                    assessment.duration_minutes * 60,
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
                attempt.status = 'timed_out'
                attempt.submitted_at = now
                attempt.save(update_fields=('status', 'submitted_at'))
                return Response({'error': 'The assessment deadline has expired.'}, status=status.HTTP_410_GONE)
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
            if attempt.status == 'graded':
                from .support_views import sync_support_eligibilities_for_user
                sync_support_eligibilities_for_user(attempt.user)
                return Response(_attempt_response(attempt))
            if attempt.status != 'in_progress':
                return Response({'error': 'This assessment attempt is no longer active.'}, status=status.HTTP_409_CONFLICT)
            now = timezone.now()
            if now >= attempt.deadline_at:
                attempt.status = 'timed_out'
                attempt.submitted_at = now
                attempt.save(update_fields=('status', 'submitted_at'))
                return Response({'error': 'The assessment deadline has expired.'}, status=status.HTTP_410_GONE)
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
            from .support_views import sync_support_eligibilities_for_user
            sync_support_eligibilities_for_user(attempt.user)
        return Response(_attempt_response(attempt))
