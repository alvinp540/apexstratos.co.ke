from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
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


def contest_window_for(value):
    local_date = timezone.localtime(value).date()
    if local_date.weekday() not in (4, 5, 6):
        return None

    friday = local_date - timedelta(days=local_date.weekday() - 4)
    start = timezone.make_aware(
        datetime.combine(friday, time.min),
        timezone.get_current_timezone(),
    )
    return start, start + timedelta(days=3)


def _assessment_is_ready(assessment):
    if assessment.duration_minutes != 20:
        return False
    if not assessment.video or not assessment.video.storage.exists(assessment.video.name):
        return False
    questions = list(assessment.questions.order_by('order'))
    if len(questions) != 5 or [question.order for question in questions] != [1, 2, 3, 4, 5]:
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
        'video_url': assessment.video.url,
        'questions': [
            {
                'id': str(question.id),
                'order': question.order,
                'prompt': question.prompt,
                'options': question.options,
                'correct_answer': question.correct_answer,
                'rationale': question.rationale,
            }
            for question in assessment.questions.order_by('order')
        ],
        'scoring_rule': 'Each of five questions is worth 20 percentage points.',
    }


def _attempt_response(attempt):
    remaining = max(
        0,
        int((attempt.deadline_at - timezone.now()).total_seconds()),
    ) if attempt.deadline_at else 0
    snapshot = attempt.assessment_snapshot
    questions = [
        {
            'id': question['id'],
            'order': question['order'],
            'prompt': question['prompt'],
            'options': question['options'],
        }
        for question in snapshot.get('questions', [])
    ]
    return {
        'id': str(attempt.id),
        'assessment': str(attempt.assessment_id),
        'title': snapshot.get('title', attempt.assessment.title),
        'field': snapshot.get('field', attempt.assessment.field),
        'description': snapshot.get('description', attempt.assessment.description),
        'video_url': snapshot.get('video_url'),
        'questions': questions,
        'answers': attempt.answers,
        'status': attempt.status,
        'score': attempt.score,
        'started_at': attempt.started_at,
        'deadline_at': attempt.deadline_at,
        'server_time': timezone.now(),
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
        local_now = timezone.localtime(now)
        if local_now.weekday() not in (4, 5, 6):
            return Response([])

        entitlements = ParticipationPayment.objects.filter(
            user=request.user,
            status='verified',
            expires_at__gt=now,
        ).values_list('field', flat=True)
        if not entitlements:
            return Response([])

        friday = local_now.date() - timedelta(days=local_now.weekday() - 4)
        window_start = timezone.make_aware(
            datetime.combine(friday, time.min),
            timezone.get_current_timezone(),
        )
        window_end = window_start + timedelta(days=3)
        assessments = AssessmentSchedule.objects.filter(
            field__in=entitlements,
            status__in=('published', 'scheduled'),
            scheduled_for__gte=window_start,
            scheduled_for__lt=window_end,
        ).prefetch_related('questions').order_by('field', 'day', 'assessment_slot')

        results = []
        for assessment in assessments:
            window = contest_window_for(assessment.scheduled_for)
            if not window or not (window[0] <= now < window[1]):
                continue
            if not _assessment_is_ready(assessment):
                continue
            attempt = AssessmentScheduleAttempt.objects.filter(
                user=request.user,
                assessment=assessment,
            ).first()
            results.append({
                'id': str(assessment.id),
                'title': assessment.title,
                'field': assessment.field,
                'description': assessment.description,
                'day': assessment.day,
                'assessment_slot': assessment.assessment_slot,
                'scheduled_for': assessment.scheduled_for,
                'video_url': assessment.video.url,
                'duration_minutes': 20,
                'window_closes_at': window[1],
                'attempt': _attempt_response(attempt) if attempt else None,
            })
        return Response(results)


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
            window = contest_window_for(assessment.scheduled_for)
            if not window or not (window[0] <= now < window[1]):
                return Response(
                    {'error': 'This assessment is only available during its published Friday-to-Sunday contest window.'},
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
                    {'error': 'This assessment is not available because its video or question set is incomplete.'},
                    status=status.HTTP_409_CONFLICT,
                )

            attempt, created = AssessmentScheduleAttempt.objects.get_or_create(
                user=request.user,
                assessment=assessment,
                defaults={
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
                attempt.deadline_at = _attempt_deadline(
                    attempt.started_at,
                    attempt.duration_seconds,
                    window[1],
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
            if any(
                str(question_id) not in questions
                or answer not in questions[str(question_id)]['options']
                for question_id, answer in answers.items()
            ):
                return Response(
                    {'error': 'One or more answers are not valid for this assessment version.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            normalized_answers = {str(question_id): answer for question_id, answer in answers.items()}
            attempt.answers = normalized_answers
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

        return Response({
            'attempt_id': str(attempt.id),
            'status': attempt.status,
            'score': attempt.score,
            'submitted_at': attempt.submitted_at,
            'is_flagged': attempt.is_flagged,
        })
