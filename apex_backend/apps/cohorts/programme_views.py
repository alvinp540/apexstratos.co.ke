import json
from collections import defaultdict
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
from apps.notifications.utils import send_notification
from utils.pagination import StandardResultsPagination
from .models import (
    AssessmentSchedule,
    AssessmentScheduleAttempt,
    ParticipationPayment,
    ParticipationPaymentEvent,
)
from .tutorial_schedule import CAPABILITY_FIELDS
from .views import _get_client_ip
from .weekly_schedule import (
    EAT,
    activity_window,
    attempt_deadline as weekly_attempt_deadline,
    next_opening as weekly_next_opening,
)


def contest_window_for(value):
    local_date = value.astimezone(EAT).date()
    if local_date.weekday() not in (4, 5, 6):
        return None

    friday = local_date - timedelta(days=local_date.weekday() - 4)
    start = timezone.make_aware(datetime.combine(friday, time.min), EAT)
    return start, start + timedelta(days=3)


def _assessment_is_ready(assessment):
    if assessment.duration_minutes != 20:
        return False
    questions = list(assessment.questions.order_by('order'))
    if len(questions) != 10 or [question.order for question in questions] != list(range(1, 11)):
        return False
    return all(
        question.question_type == 'multiple_choice'
        and isinstance(question.options, list)
        and len(question.options) >= 2
        and question.correct_answer in question.options
        for question in questions
    )


def _attempt_deadline(started_at, duration_seconds, contest_deadline):
    attempt_deadline = started_at + timedelta(seconds=duration_seconds)
    return min(attempt_deadline, contest_deadline)


def _snapshot(assessment):
    return {
        'title': assessment.title,
        'field': assessment.field,
        'description': assessment.description,
        'questions': [
            {
                'id': str(question.id),
                'order': question.order,
                'prompt': question.prompt,
                'options': question.options,
                'correct_answer': question.correct_answer,
                'rationale': question.rationale,
                'requires_reasoning': question.requires_reasoning,
            }
            for question in assessment.questions.order_by('order')
        ],
        'scoring_rule': 'Each of ten questions is worth 10 percentage points.',
    }


def _attempt_response(attempt):
    now = timezone.now()
    remaining = max(
        0,
        int((attempt.deadline_at - now).total_seconds()),
    ) if attempt.deadline_at else 0
    snapshot = attempt.assessment_snapshot
    answers = {}
    reasoning = {}
    for question_id, value in attempt.answers.items():
        answers[question_id] = value.get('answer', '') if isinstance(value, dict) else value
        if isinstance(value, dict) and value.get('reasoning'):
            reasoning[question_id] = value['reasoning']
    questions = [
        {
            'id': question['id'],
            'order': question['order'],
            'prompt': question['prompt'],
            'options': question['options'],
            'requires_reasoning': question.get('requires_reasoning', False),
            **(
                {
                    'correct_answer': question['correct_answer'],
                    'rationale': question['rationale'],
                    'selected_answer': answers.get(question['id']),
                }
                if attempt.status == 'graded'
                else {}
            ),
        }
        for question in snapshot.get('questions', [])
    ]
    attempt_status = attempt.status
    if attempt_status == 'in_progress' and attempt.deadline_at and now >= attempt.deadline_at:
        attempt_status = 'timed_out'
    return {
        'id': str(attempt.id),
        'assessment': str(attempt.assessment_id),
        'title': snapshot.get('title', attempt.assessment.title),
        'field': snapshot.get('field', attempt.assessment.field),
        'description': snapshot.get('description', attempt.assessment.description),
        'questions': questions,
        'answers': answers,
        'reasoning': reasoning,
        'status': attempt_status,
        'score': attempt.score,
        'started_at': attempt.started_at,
        'deadline_at': attempt.deadline_at,
        'server_time': now,
        'time_remaining': remaining,
        'is_flagged': attempt.is_flagged,
    }


class ParticipationPaymentSubmissionSerializer(serializers.ModelSerializer):
    program = serializers.ChoiceField(
        choices=(('main_contest', 'Main contests'),),
        write_only=True,
    )

    class Meta:
        model = ParticipationPayment
        fields = (
            'id', 'full_name', 'phone_number', 'field', 'program', 'amount_kes',
            'till_number', 'payment_reference', 'status', 'created_at',
            'verified_at', 'rejection_reason',
        )
        read_only_fields = (
            'id', 'till_number', 'status', 'created_at', 'verified_at',
            'rejection_reason',
        )
        extra_kwargs = {
            'full_name': {'required': True},
            'phone_number': {'required': True},
            'field': {'required': True},
            'amount_kes': {'required': True},
            'payment_reference': {'required': True, 'allow_null': False},
        }

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter your full name.')
        profile = getattr(self.context['request'].user, 'profile', None)
        registered_name = getattr(profile, 'full_name', '').strip()
        if registered_name and value.casefold() != registered_name.casefold():
            raise serializers.ValidationError(
                'Use the name recorded on your ApexStratos profile.'
            )
        return value

    def validate_phone_number(self, value):
        user_phone = (self.context['request'].user.phone_number or '').strip()
        if not user_phone or value.strip() != user_phone:
            raise serializers.ValidationError(
                'Use the phone number registered to your ApexStratos account.'
            )
        return user_phone

    def validate_amount_kes(self, value):
        if value != 100:
            raise serializers.ValidationError('Main contest access costs KSh 100.')
        return value

    def validate_payment_reference(self, value):
        value = value.strip().upper()
        if len(value) < 5:
            raise serializers.ValidationError('Enter the M-Pesa transaction reference.')
        if ParticipationPayment.objects.filter(payment_reference=value).exists():
            raise serializers.ValidationError(
                'This M-Pesa transaction reference has already been submitted.'
            )
        return value

    def validate(self, attrs):
        if attrs.get('field') not in CAPABILITY_FIELDS:
            raise serializers.ValidationError({'field': 'Choose an official study area.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('program')
        return super().create(validated_data)


class ParticipationPaymentListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        payments = ParticipationPayment.objects.filter(user=request.user).order_by('-created_at')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(payments, request)
        return paginator.get_paginated_response(
            ParticipationPaymentSubmissionSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = ParticipationPaymentSubmissionSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                payment = serializer.save(
                    user=request.user,
                    till_number='1598106',
                    status='pending',
                )
                ParticipationPaymentEvent.objects.create(
                    payment=payment,
                    actor=request.user,
                    decision='submitted',
                )
        except IntegrityError:
            raise serializers.ValidationError({
                'payment_reference': 'This M-Pesa transaction reference has already been submitted.'
            })
        return Response(
            ParticipationPaymentSubmissionSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )


class ParticipationPaymentAdminListView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        payments = ParticipationPayment.objects.select_related(
            'user', 'verified_by',
        ).prefetch_related('events__actor').order_by('created_at')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(payments, request)
        return paginator.get_paginated_response([
            {
                'id': str(payment.id),
                'program': 'main_contest',
                'user_id': str(payment.user_id),
                'email': payment.user.email,
                'full_name': payment.full_name,
                'phone_number': payment.phone_number,
                'field': payment.field,
                'amount_kes': payment.amount_kes,
                'till_number': payment.till_number,
                'payment_reference': payment.payment_reference,
                'mpesa_transaction_id': payment.mpesa_transaction_id,
                'status': payment.status,
                'verification_notes': payment.verification_notes,
                'rejection_reason': payment.rejection_reason,
                'verified_by': str(payment.verified_by_id) if payment.verified_by_id else None,
                'created_at': payment.created_at,
                'verified_at': payment.verified_at,
                'expires_at': payment.expires_at,
                'events': [
                    {
                        'decision': event.decision,
                        'actor': str(event.actor_id) if event.actor_id else None,
                        'notes': event.notes,
                        'created_at': event.created_at,
                    }
                    for event in payment.events.all()
                ],
            }
            for payment in page
        ])


class ParticipationPaymentDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=('under_review', 'verified', 'rejected'))
    verification_notes = serializers.CharField(required=False, allow_blank=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    confirmed_transaction_id = serializers.CharField(required=False, allow_blank=True, max_length=255)
    expires_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        decision = attrs['decision']
        if decision == 'verified':
            if not attrs.get('verification_notes', '').strip():
                raise serializers.ValidationError({
                    'verification_notes': 'Record how the transaction was checked against payment evidence.'
                })
            transaction_id = attrs.get('confirmed_transaction_id', '').strip().upper()
            if not transaction_id:
                raise serializers.ValidationError({
                    'confirmed_transaction_id': 'Enter the transaction ID confirmed from payment evidence.'
                })
            if ParticipationPayment.objects.exclude(pk=self.context['payment_id']).filter(
                mpesa_transaction_id=transaction_id
            ).exists():
                raise serializers.ValidationError({
                    'confirmed_transaction_id': 'This confirmed transaction is already linked to a payment.'
                })
            attrs['confirmed_transaction_id'] = transaction_id
            expires_at = attrs.get('expires_at')
            if not expires_at or expires_at <= timezone.now():
                raise serializers.ValidationError({
                    'expires_at': 'Set the end of the authorized main contest access period before verification.'
                })
        if decision == 'rejected' and not attrs.get('rejection_reason', '').strip():
            raise serializers.ValidationError({
                'rejection_reason': 'Provide a reason for rejecting this payment request.'
            })
        if decision == 'under_review' and not attrs.get('verification_notes', '').strip():
            raise serializers.ValidationError({
                'verification_notes': 'Record why the payment requires further review.'
            })
        return attrs


class ParticipationPaymentDecisionView(APIView):
    permission_classes = (IsAdmin,)

    def post(self, request, payment_id):
        serializer = ParticipationPaymentDecisionSerializer(
            data=request.data,
            context={'payment_id': payment_id},
        )
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data['decision']

        try:
            with transaction.atomic():
                payment = get_object_or_404(
                    ParticipationPayment.objects.select_for_update().select_related('user'),
                    id=payment_id,
                )
                if payment.status in ('verified', 'rejected'):
                    if payment.status == decision:
                        return Response(ParticipationPaymentSubmissionSerializer(payment).data)
                    return Response(
                        {'error': 'A final payment decision has already been recorded.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                if payment.status not in ('pending', 'under_review'):
                    return Response(
                        {'error': 'This payment request is not in a reviewable state.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                if decision == 'verified' and (
                    payment.amount_kes != 100 or payment.till_number != '1598106'
                ):
                    return Response(
                        {'error': 'The payment amount or Till number does not match the main contest programme.'},
                        status=status.HTTP_409_CONFLICT,
                    )

                payment.status = decision
                payment.verified_by = request.user
                payment.verification_notes = serializer.validated_data.get('verification_notes', '').strip()
                payment.rejection_reason = serializer.validated_data.get('rejection_reason', '').strip()
                if decision == 'verified':
                    payment.mpesa_transaction_id = serializer.validated_data['confirmed_transaction_id'].upper()
                    payment.verified_at = timezone.now()
                    payment.expires_at = serializer.validated_data['expires_at']
                payment.save(update_fields=(
                    'status', 'verified_by', 'verification_notes', 'rejection_reason',
                    'mpesa_transaction_id', 'verified_at', 'expires_at',
                ))
                ParticipationPaymentEvent.objects.create(
                    payment=payment,
                    actor=request.user,
                    decision=decision,
                    notes=(
                        payment.rejection_reason
                        if decision == 'rejected'
                        else payment.verification_notes
                    ),
                    confirmed_transaction_id=payment.mpesa_transaction_id or '',
                )

                if decision in ('verified', 'rejected'):
                    title = 'Main contest payment verified' if decision == 'verified' else 'Main contest payment not verified'
                    message = (
                        'Your KSh 100 main contest payment was verified. Access is now available for '
                        f'{payment.field} assessments during their published contest windows.'
                        if decision == 'verified'
                        else f'Your main contest payment request was rejected. {payment.rejection_reason}'
                    )
                    send_notification(
                        user=payment.user,
                        notification_type='payment',
                        title=title,
                        message=message,
                        action_url='/contests',
                        metadata={'payment_id': str(payment.id), 'status': decision},
                    )
        except IntegrityError:
            return Response(
                {'error': 'This confirmed M-Pesa transaction is already linked to another payment.'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(ParticipationPaymentSubmissionSerializer(payment).data)


class ContestAssessmentListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        now = timezone.now()
        entitlements = set(ParticipationPayment.objects.filter(
            user=request.user,
            status='verified',
            expires_at__gt=now,
        ).values_list('field', flat=True))
        attempts = {
            attempt.assessment_id: attempt
            for attempt in AssessmentScheduleAttempt.objects.filter(user=request.user)
            .select_related('assessment')
        }
        window = activity_window('main_contest', now)
        assessments = AssessmentSchedule.objects.filter(
            status__in=('published', 'scheduled'),
        ).prefetch_related('questions').order_by('field', 'day', 'assessment_slot')

        results = []
        for assessment in assessments:
            if not _assessment_is_ready(assessment):
                continue
            attempt = attempts.get(assessment.id)
            entitled = assessment.field in entitlements
            if not entitled and attempt is None:
                continue
            results.append({
                'id': str(assessment.id),
                'title': assessment.title,
                'field': assessment.field,
                'description': assessment.description,
                'day': assessment.day,
                'assessment_slot': assessment.assessment_slot,
                'scheduled_for': assessment.scheduled_for,
                'duration_minutes': 20,
                'can_start': bool(entitled and window),
                'window_closes_at': window[1] if window else None,
                'next_opening_at': None if window else weekly_next_opening('main_contest', now),
                'attempt': _attempt_response(attempt) if attempt else None,
            })
        return Response(results)


class ContestLibraryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        filters = {}
        field = request.query_params.get('field')
        if field:
            if field not in CAPABILITY_FIELDS:
                raise serializers.ValidationError({'field': 'Choose an official study area.'})
            filters['field'] = field
        week_value = request.query_params.get('week')
        if week_value:
            try:
                library_week = int(week_value)
            except (TypeError, ValueError):
                raise serializers.ValidationError({'week': 'Week must be between 1 and 8.'})
            if not 1 <= library_week <= 8:
                raise serializers.ValidationError({'week': 'Week must be between 1 and 8.'})
            filters['month'] = (library_week - 1) // 4 + 1
            filters['week'] = (library_week - 1) % 4 + 1
        topic = serializers.CharField(max_length=120, allow_blank=True).run_validation(
            request.query_params.get('topic', ''),
        ).strip()

        assessments_query = AssessmentSchedule.objects.filter(
            status__in=('published', 'scheduled'),
        ).filter(**filters)
        if topic:
            assessments_query = assessments_query.filter(
                Q(title__icontains=topic) | Q(description__icontains=topic),
            )
        assessments = list(assessments_query.prefetch_related('questions').order_by(
            'month', 'week', 'field', 'day', 'assessment_slot',
        ))
        now = timezone.now()
        window = activity_window('main_contest', now)
        entitlement_fields = set(ParticipationPayment.objects.filter(
            user=request.user,
            status='verified',
            expires_at__gt=now,
        ).values_list('field', flat=True))
        attempts = {
            attempt.assessment_id: attempt
            for attempt in AssessmentScheduleAttempt.objects.filter(
                user=request.user,
                assessment__in=assessments,
            ).select_related('assessment')
        }
        results = []
        for assessment in assessments:
            if not _assessment_is_ready(assessment):
                continue
            attempt = attempts.get(assessment.id)
            entitled = assessment.field in entitlement_fields
            results.append({
                'id': str(assessment.id),
                'title': assessment.title,
                'field': assessment.field,
                'week': (assessment.month - 1) * 4 + assessment.week,
                'description': assessment.description,
                'day': assessment.day,
                'assessment_slot': assessment.assessment_slot,
                'scheduled_for': assessment.scheduled_for,
                'question_count': 10,
                'duration_minutes': 20,
                'access_price_kes': 100,
                'has_verified_access': entitled,
                'can_start': entitled and window is not None,
                'window_closes_at': window[1] if window else None,
                'next_opening_at': None if window else weekly_next_opening('main_contest', now),
                'attempt': _attempt_response(attempt) if attempt else None,
            })
        return Response({'count': len(results), 'results': results})


class StartContestAssessmentView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, assessment_id):
        with transaction.atomic():
            assessment = get_object_or_404(
                AssessmentSchedule.objects.select_for_update().prefetch_related('questions'),
                id=assessment_id,
                status__in=('published', 'scheduled'),
            )
            now = timezone.now()
            window = activity_window('main_contest', now)
            if not window:
                return Response(
                    {'error': 'Main Contest assessments are available Friday through Sunday in EAT.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not ParticipationPayment.objects.filter(
                user=request.user,
                field=assessment.field,
                status='verified',
                expires_at__gt=now,
            ).exists():
                return Response(
                    {'error': 'Verified main contest payment for this study area is required.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not _assessment_is_ready(assessment):
                return Response(
                    {'error': 'This assessment is not available because its ten-question set is incomplete or invalid.'},
                    status=status.HTTP_409_CONFLICT,
                )

            attempt, created = AssessmentScheduleAttempt.objects.get_or_create(
                user=request.user,
                assessment=assessment,
                defaults={
                    'started_at': now,
                    'question_order': [
                        str(question.id)
                        for question in assessment.questions.order_by('order')
                    ],
                    'assessment_snapshot': _snapshot(assessment),
                    'duration_seconds': assessment.duration_minutes * 60,
                    'ip_address': _get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                },
            )
            if created:
                attempt.deadline_at = weekly_attempt_deadline(
                    'main_contest',
                    attempt.started_at,
                    attempt.duration_seconds,
                )
                attempt.save(update_fields=('deadline_at',))
            elif attempt.status != 'in_progress':
                return Response(
                    {'error': 'This assessment has already been submitted.'},
                    status=status.HTTP_409_CONFLICT,
                )
            elif not attempt.assessment_snapshot:
                return Response(
                    {'error': 'This attempt has no preserved assessment version and cannot be safely resumed.'},
                    status=status.HTTP_409_CONFLICT,
                )
            elif not attempt.deadline_at or now >= attempt.deadline_at:
                attempt.status = 'timed_out'
                attempt.submitted_at = now
                attempt.save(update_fields=('status', 'submitted_at'))
                return Response(
                    {'error': 'The assessment deadline has expired.'},
                    status=status.HTTP_410_GONE,
                )
        return Response(_attempt_response(attempt), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SaveContestAttemptAnswersView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, attempt_id):
        with transaction.atomic():
            attempt = get_object_or_404(
                AssessmentScheduleAttempt.objects.select_for_update(),
                id=attempt_id,
                user=request.user,
            )
            if attempt.status != 'in_progress':
                return Response(
                    {'error': 'This assessment attempt is no longer active.'},
                    status=status.HTTP_409_CONFLICT,
                )
            now = timezone.now()
            if not attempt.deadline_at or now >= attempt.deadline_at:
                attempt.status = 'timed_out'
                attempt.submitted_at = now
                attempt.save(update_fields=('status', 'submitted_at'))
                return Response(
                    {'error': 'The assessment deadline has expired.'},
                    status=status.HTTP_410_GONE,
                )
            answers = request.data.get('answers', {})
            reasoning = request.data.get('reasoning', {})
            if not isinstance(answers, dict) or not isinstance(reasoning, dict):
                return Response(
                    {'error': 'Answers and reasoning must be question-to-value maps.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            questions = {
                question['id']: question
                for question in attempt.assessment_snapshot.get('questions', [])
            }
            normalized = dict(attempt.answers)
            for raw_id, answer in answers.items():
                question_id = str(raw_id)
                if question_id not in questions or answer not in questions[question_id]['options']:
                    return Response(
                        {'error': 'One or more answers are invalid for this assessment version.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                old_value = normalized.get(question_id, {})
                normalized[question_id] = {
                    'answer': answer,
                    'reasoning': old_value.get('reasoning', '') if isinstance(old_value, dict) else '',
                }
            for raw_id, text in reasoning.items():
                question_id = str(raw_id)
                if question_id not in questions or not isinstance(text, str) or len(text) > 5000:
                    return Response(
                        {'error': 'One or more written reasoning responses are invalid.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                old_value = normalized.get(question_id, {})
                normalized[question_id] = {
                    'answer': old_value.get('answer', '') if isinstance(old_value, dict) else old_value,
                    'reasoning': text,
                }
            attempt.answers = normalized
            attempt.save(update_fields=('answers',))
        return Response(_attempt_response(attempt))


class SubmitContestAssessmentView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, attempt_id):
        with transaction.atomic():
            attempt = get_object_or_404(
                AssessmentScheduleAttempt.objects.select_for_update(),
                id=attempt_id,
                user=request.user,
            )
            if attempt.status == 'graded':
                from .support_views import sync_support_eligibilities_for_user
                sync_support_eligibilities_for_user(attempt.user)

                return Response({
                    'attempt_id': str(attempt.id),
                    'status': attempt.status,
                    'score': attempt.score,
                    'submitted_at': attempt.submitted_at,
                    'is_flagged': attempt.is_flagged,
                })

            if attempt.status != 'in_progress':
                return Response(
                    {'error': 'This assessment attempt is no longer active.'},
                    status=status.HTTP_409_CONFLICT,
                )
            now = timezone.now()
            if not attempt.deadline_at or now >= attempt.deadline_at:
                attempt.status = 'timed_out'
                attempt.submitted_at = now
                attempt.save(update_fields=('status', 'submitted_at'))
                return Response(
                    {'error': 'The assessment deadline has expired.'},
                    status=status.HTTP_410_GONE,
                )

            answers = request.data.get('answers')
            if not isinstance(answers, dict):
                return Response(
                    {'error': 'Answers must be submitted as a question-to-answer map.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            question_snapshot = attempt.assessment_snapshot.get('questions', [])
            questions = {question['id']: question for question in question_snapshot}
            normalized_answers = {str(question_id): answer for question_id, answer in answers.items()}
            if any(
                question_id not in questions
                or answer not in questions[question_id]['options']
                for question_id, answer in normalized_answers.items()
            ):
                return Response(
                    {'error': 'One or more answers are not valid for this assessment version.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            reasoning = request.data.get('reasoning', {})
            if not isinstance(reasoning, dict):
                return Response(
                    {'error': 'Written reasoning must be submitted as a question-to-text map.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            normalized_reasoning = {}
            for question_id, text in reasoning.items():
                question_id = str(question_id)
                if question_id not in questions or not isinstance(text, str) or len(text) > 5000:
                    return Response(
                        {'error': 'One or more written reasoning responses are invalid.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if text.strip():
                    normalized_reasoning[question_id] = text.strip()
            if any(
                question.get('requires_reasoning')
                and not normalized_reasoning.get(question['id'])
                for question in question_snapshot
            ):
                return Response(
                    {'error': 'Written reasoning is required for one or more questions.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            attempt.answers = {
                question_id: {
                    'answer': answer,
                    'reasoning': normalized_reasoning.get(question_id, ''),
                }
                for question_id, answer in normalized_answers.items()
            }
            attempt.submitted_at = now
            attempt.status = 'graded'
            attempt.ip_address = _get_client_ip(request)
            attempt.score = round(
                100 * sum(
                    normalized_answers.get(question['id']) == question['correct_answer']
                    for question in question_snapshot
                ) / len(question_snapshot),
                2,
            )
            attempt.save(update_fields=(
                'answers', 'submitted_at', 'status', 'ip_address', 'score',
            ))
            from .support_views import sync_support_eligibilities_for_user
            sync_support_eligibilities_for_user(attempt.user)

        return Response({
            'attempt_id': str(attempt.id),
            'status': attempt.status,
            'score': attempt.score,
            'submitted_at': attempt.submitted_at,
            'is_flagged': attempt.is_flagged,
        })


class MyContestCycleLeaderboardView(APIView):
    permission_classes = (IsAuthenticated,)

    @staticmethod
    def _assessment_set_key(attempts):
        key = []
        elapsed_seconds = 0
        for attempt in attempts:
            snapshot = attempt['assessment_snapshot']
            if (
                not isinstance(snapshot, dict)
                or not isinstance(snapshot.get('questions'), list)
                or not snapshot.get('questions')
                or not attempt['started_at']
                or not attempt['submitted_at']
            ):
                return None, None
            elapsed = (attempt['submitted_at'] - attempt['started_at']).total_seconds()
            if elapsed <= 0:
                return None, None
            try:
                question_set = json.dumps(
                    {
                        'questions': snapshot['questions'],
                        'scoring_rule': snapshot.get('scoring_rule'),
                    },
                    sort_keys=True,
                    separators=(',', ':'),
                )
            except (TypeError, ValueError):
                return None, None
            key.append((str(attempt['assessment_id']), question_set))
            elapsed_seconds += elapsed
        return tuple(sorted(key)), elapsed_seconds

    def get(self, request):
        attempts = AssessmentScheduleAttempt.objects.filter(
            user=request.user,
            status='graded',
            score__isnull=False,
            is_flagged=False,
            submitted_at__isnull=False,
        ).select_related('assessment').order_by('-submitted_at')
        latest = attempts.first()
        if latest is None:
            return Response({
                'rank': None,
                'field': None,
                'cycle_start': None,
                'cycle_end': None,
                'average_score': None,
                'attempt_count': 0,
                'participant_count': 0,
                'ranking_status': 'provisional',
                'cycle_kind': 'weekly_contest',
                'tie_break_seconds': None,
                'tie_break_applied': False,
                'ranking_method': (
                    'Provisional weekly contest rank by average score. Elapsed time is '
                    'only a tie-break for tied participants with the same assessment IDs, '
                    'question snapshots, and scoring rules; otherwise tied scores share a rank.'
                ),
            })

        latest_local_date = latest.submitted_at.astimezone(EAT).date()
        friday = latest_local_date - timedelta(days=(latest_local_date.weekday() - 4) % 7)
        cycle_start = timezone.make_aware(datetime.combine(friday, time.min), EAT)
        cycle_end = cycle_start + timedelta(days=3)
        cycle_attempts = list(
            AssessmentScheduleAttempt.objects.filter(
                assessment__field=latest.assessment.field,
                status='graded',
                score__isnull=False,
                is_flagged=False,
                submitted_at__gte=cycle_start,
                submitted_at__lt=cycle_end,
            ).values(
                'user_id',
                'assessment_id',
                'score',
                'started_at',
                'submitted_at',
                'assessment_snapshot',
            ).order_by('user_id', 'assessment_id')
        )
        attempts_by_user = defaultdict(list)
        for attempt in cycle_attempts:
            attempts_by_user[attempt['user_id']].append(attempt)

        cycle_scores = []
        for user_id, attempts_for_user in attempts_by_user.items():
            assessment_set, elapsed_seconds = self._assessment_set_key(attempts_for_user)
            cycle_scores.append({
                'user_id': user_id,
                'average_score': round(
                    sum(attempt['score'] for attempt in attempts_for_user) / len(attempts_for_user),
                    2,
                ),
                'attempt_count': len(attempts_for_user),
                'assessment_set': assessment_set,
                'elapsed_seconds': elapsed_seconds,
            })
        cycle_scores.sort(key=lambda entry: (-entry['average_score'], entry['user_id']))

        rank = None
        average_score = None
        attempt_count = 0
        tie_break_seconds = None
        tie_break_applied = False
        start_index = 0
        while start_index < len(cycle_scores):
            end_index = start_index + 1
            score = cycle_scores[start_index]['average_score']
            while (
                end_index < len(cycle_scores)
                and cycle_scores[end_index]['average_score'] == score
            ):
                end_index += 1
            score_group = cycle_scores[start_index:end_index]
            assessment_sets = {entry['assessment_set'] for entry in score_group}
            comparable = (
                len(score_group) > 1
                and len(assessment_sets) == 1
                and None not in assessment_sets
                and all(entry['elapsed_seconds'] is not None for entry in score_group)
            )
            block_tie_break_applied = False
            if comparable:
                score_group.sort(key=lambda entry: (entry['elapsed_seconds'], entry['user_id']))
                elapsed_groups = []
                for entry in score_group:
                    if not elapsed_groups or elapsed_groups[-1][0]['elapsed_seconds'] != entry['elapsed_seconds']:
                        elapsed_groups.append([entry])
                    else:
                        elapsed_groups[-1].append(entry)
                ordered_groups = []
                group_index = 0
                for elapsed_group in elapsed_groups:
                    ordered_groups.append((start_index + group_index + 1, elapsed_group))
                    group_index += len(elapsed_group)
                block_tie_break_applied = len(elapsed_groups) > 1
            else:
                ordered_groups = [(start_index + 1, score_group)]

            for group_rank, entries in ordered_groups:
                if any(entry['user_id'] == request.user.id for entry in entries):
                    student_entry = next(
                        entry for entry in entries if entry['user_id'] == request.user.id
                    )
                    rank = group_rank
                    average_score = student_entry['average_score']
                    attempt_count = student_entry['attempt_count']
                    tie_break_applied = block_tie_break_applied
                    tie_break_seconds = (
                        student_entry['elapsed_seconds']
                        if comparable
                        else None
                    )
                    break
            if rank is not None:
                break
            start_index = end_index

        return Response({
            'rank': rank,
            'field': latest.assessment.field,
            'cycle_start': cycle_start,
            'cycle_end': cycle_end,
            'average_score': average_score,
            'attempt_count': attempt_count,
            'participant_count': len(cycle_scores),
            'ranking_status': 'provisional',
            'cycle_kind': 'weekly_contest',
            'tie_break_seconds': tie_break_seconds,
            'tie_break_applied': tie_break_applied,
            'ranking_method': (
                'Provisional weekly contest rank by average score across verified, unflagged '
                'Main Contest attempts in a Friday–Sunday East Africa Time cycle. When tied '
                'participants have identical assessment IDs, question snapshots, and scoring '
                'rules, shorter server-recorded elapsed time ranks higher; equal elapsed times '
                'share a rank. Tied scores across different or unverifiable assessment sets '
                'share a rank.'
            ),
        })
