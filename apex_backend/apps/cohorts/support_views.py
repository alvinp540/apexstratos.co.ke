import re

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin
from apps.notifications.utils import send_notification
from apps.profiles.models import Profile
from .models import (
    AssessmentScheduleAttempt,
    SupportApplication,
    SupportEligibility,
    SupportApplicationEvent,
    SupportProgram,
    TutorialProgress,
)


class SupportApplicationInputSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    registered_phone_number = serializers.CharField(max_length=20)
    mpesa_number = serializers.CharField(max_length=20)

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter your registered full name.')
        return value

    def validate_registered_phone_number(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter your registered phone number.')
        return value

    def validate_mpesa_number(self, value):
        value = re.sub(r'[\s-]', '', value)
        if not re.fullmatch(r'(?:\+?254|0)\d{9}', value):
            raise serializers.ValidationError('Enter a valid Kenyan M-Pesa number.')
        return value


class SupportApplicationSerializer(serializers.ModelSerializer):
    program_title = serializers.CharField(source='program_title_at_application', read_only=True)
    program_type = serializers.CharField(source='program_type_at_application', read_only=True)
    events = serializers.SerializerMethodField()

    class Meta:
        model = SupportApplication
        fields = (
            'id', 'program', 'program_title', 'program_type', 'full_name',
            'registered_phone_number', 'mpesa_number', 'merit_score_at_application',
            'tutorial_consistency_weeks_at_application', 'status', 'admin_reason',
            'payment_reference', 'payment_confirmed_at', 'submitted_at', 'updated_at',
            'events',
        )
        read_only_fields = fields

    def get_events(self, obj):
        return [
            {
                'status': event.status,
                'reason': event.reason,
                'payment_reference': event.payment_reference,
                'created_at': event.created_at,
            }
            for event in obj.events.all()
        ]


class SupportApplicationAdminDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SupportApplication.STATUS_CHOICES)
    admin_reason = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    payment_reference = serializers.CharField(required=False, allow_blank=True, max_length=255)


def get_support_merit(user):
    scores = AssessmentScheduleAttempt.objects.filter(
        user=user,
        status='graded',
        score__isnull=False,
        is_flagged=False,
    ).aggregate(average=Avg('score'), count=Count('id'))
    completed_weeks = {
        (month - 1) * 4 + week
        for month, week in TutorialProgress.objects.filter(
            user=user,
            completed_at__isnull=False,
        ).values_list('tutorial__month', 'tutorial__week')
    }
    return round(scores['average'] or 0, 2), scores['count'], len(completed_weeks)


@transaction.atomic
def sync_support_eligibility(user, program, *, merit_score=None, completed_contests=None, tutorial_weeks=None):
    if merit_score is None:
        merit_score, completed_contests, tutorial_weeks = get_support_merit(user)

    qualifies = (
        program.funding_status != 'closed'
        and completed_contests > 0
        and merit_score >= program.merit_cutoff
    )
    eligibility, created = SupportEligibility.objects.select_for_update().get_or_create(
        user=user,
        program=program,
        defaults={
            'merit_score': merit_score,
            'merit_cutoff_at_eligibility': program.merit_cutoff,
            'completed_contests': completed_contests,
            'tutorial_consistency_weeks': tutorial_weeks,
            'eligible': qualifies,
        },
    )
    has_application = SupportApplication.objects.filter(user=user, program=program).exists()
    was_eligible = eligibility.eligible
    eligibility.merit_score = merit_score
    eligibility.completed_contests = completed_contests
    eligibility.tutorial_consistency_weeks = tutorial_weeks
    eligibility.eligible = qualifies or has_application
    if qualifies and (created or not was_eligible):
        eligibility.merit_cutoff_at_eligibility = program.merit_cutoff
    should_notify = qualifies and (created or not was_eligible) and not has_application
    if should_notify:
        send_notification(
            user=user,
            notification_type='opportunity',
            title='You are eligible to apply',
            message=f'Your Main Contest merit meets the published criteria for {program.title}. Submit the private application and payment details form for review.',
            action_url='/opportunities',
            metadata={'program_id': str(program.id), 'program_type': program.program_type},
        )
        eligibility.notified_at = timezone.now()
    eligibility.save(update_fields=(
        'merit_score', 'completed_contests', 'tutorial_consistency_weeks',
        'eligible', 'notified_at', 'updated_at',
    ))
    return eligibility, merit_score, completed_contests, tutorial_weeks


def reconcile_support_program(program_id):
    program = SupportProgram.objects.get(id=program_id)
    if program.status != 'published' or (program.deadline and program.deadline <= timezone.now()):
        SupportEligibility.objects.filter(program=program, eligible=True).exclude(
            applications__isnull=False,
        ).update(eligible=False, updated_at=timezone.now())
        return

    users = User.objects.filter(
        assessment_attempts__status='graded',
        assessment_attempts__score__isnull=False,
        assessment_attempts__is_flagged=False,
    ).distinct()
    for user in users.iterator():
        sync_support_eligibility(user, program)


def sync_support_eligibilities_for_user(user):
    now = timezone.now()
    programs = SupportProgram.objects.filter(status='published').filter(
        Q(deadline__isnull=True) | Q(deadline__gt=now),
    )
    merit_score, completed_contests, tutorial_weeks = get_support_merit(user)
    for program in programs:
        sync_support_eligibility(
            user,
            program,
            merit_score=merit_score,
            completed_contests=completed_contests,
            tutorial_weeks=tutorial_weeks,
        )


class SupportProgramListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        now = timezone.now()
        programs = SupportProgram.objects.filter(
            status='published',
        ).filter(
            Q(deadline__isnull=True) | Q(deadline__gt=now),
        ).order_by('deadline', 'title')
        merit_score, completed_contests, tutorial_weeks = get_support_merit(request.user)
        applications = {
            application.program_id: application
            for application in SupportApplication.objects.filter(
                user=request.user,
                program__in=programs,
            ).select_related('program').prefetch_related('events')
        }
        results = []
        for program in programs:
            eligibility, _, _, _ = sync_support_eligibility(
                request.user,
                program,
                merit_score=merit_score,
                completed_contests=completed_contests,
                tutorial_weeks=tutorial_weeks,
            )
            application = applications.get(program.id)
            results.append({
                'id': str(program.id),
                'title': program.title,
                'description': program.description,
                'program_type': program.program_type,
                'eligibility_rules': program.eligibility_rules,
                'merit_cutoff': program.merit_cutoff,
                'funding_status': program.funding_status,
                'deadline': program.deadline,
                'merit_score': merit_score,
                'completed_contests': completed_contests,
                'tutorial_consistency_weeks': tutorial_weeks,
                'eligible': eligibility.eligible,
                'application': SupportApplicationSerializer(application).data if application else None,
            })
        return Response({'count': len(results), 'results': results})


class SupportApplicationListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        applications = SupportApplication.objects.filter(
            user=request.user,
        ).select_related('program').prefetch_related('events').order_by('-submitted_at')
        return Response(SupportApplicationSerializer(applications, many=True).data)


class SupportApplicationCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, program_id):
        input_serializer = SupportApplicationInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        values = input_serializer.validated_data
        now = timezone.now()

        with transaction.atomic():
            program = get_object_or_404(
                SupportProgram.objects.select_for_update(),
                id=program_id,
                status='published',
            )
            if program.deadline and program.deadline <= now:
                return Response(
                    {'error': 'The application deadline has passed.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if program.funding_status == 'closed':
                return Response(
                    {'error': 'Applications for this programme are closed.'},
                    status=status.HTTP_409_CONFLICT,
                )

            profile = Profile.objects.filter(user=request.user).first()
            registered_name = (profile.full_name if profile else '').strip()
            registered_phone = (request.user.phone_number or '').strip()
            if not registered_name or values['full_name'].casefold() != registered_name.casefold():
                return Response(
                    {'full_name': 'Use the full name registered on your ApexStratos profile.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not registered_phone or values['registered_phone_number'] != registered_phone:
                return Response(
                    {'registered_phone_number': 'Use the phone number registered to your ApexStratos account.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            eligibility, merit_score, completed_contests, tutorial_weeks = sync_support_eligibility(
                request.user,
                program,
            )
            if not eligibility.eligible or completed_contests == 0 or merit_score < program.merit_cutoff:
                return Response(
                    {'error': 'This programme is available only to students who meet its published merit cutoff.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            try:
                with transaction.atomic():
                    application = SupportApplication.objects.create(
                        user=request.user,
                        program=program,
                        eligibility=eligibility,
                        program_title_at_application=program.title,
                        program_type_at_application=program.program_type,
                        eligibility_rules_at_application=program.eligibility_rules,
                        merit_cutoff_at_application=program.merit_cutoff,
                        full_name=registered_name,
                        registered_phone_number=registered_phone,
                        mpesa_number=values['mpesa_number'],
                        merit_score_at_application=merit_score,
                        tutorial_consistency_weeks_at_application=tutorial_weeks,
                    )
            except IntegrityError:
                return Response(
                    {'error': 'An application for this programme has already been submitted.'},
                    status=status.HTTP_409_CONFLICT,
                )

            SupportApplicationEvent.objects.create(
                application=application,
                actor=request.user,
                status=application.status,
            )

        return Response(
            SupportApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )


class SupportApplicationAdminListView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        applications = SupportApplication.objects.select_related(
            'user', 'program', 'eligibility',
        ).prefetch_related('events').order_by(
            '-merit_score_at_application',
            '-tutorial_consistency_weeks_at_application',
            'submitted_at',
        )
        return Response(SupportApplicationSerializer(applications, many=True).data)


class SupportApplicationAdminDecisionView(APIView):
    permission_classes = (IsAdmin,)

    def post(self, request, application_id):
        serializer = SupportApplicationAdminDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        allowed_transitions = {
            'submitted': {'under_review', 'declined'},
            'under_review': {'approved', 'awaiting_funding', 'declined'},
            'approved': {'awaiting_funding', 'payment_processing', 'declined'},
            'awaiting_funding': {'payment_processing', 'declined'},
            'payment_processing': {'paid', 'declined'},
            'paid': set(),
            'declined': set(),
        }

        with transaction.atomic():
            application = get_object_or_404(
                SupportApplication.objects.select_for_update(),
                id=application_id,
            )
            next_status = values['status']
            if next_status != application.status and next_status not in allowed_transitions[application.status]:
                return Response(
                    {'status': 'This application status transition is not allowed.'},
                    status=status.HTTP_409_CONFLICT,
                )
            reason = values.get('admin_reason', application.admin_reason).strip()
            payment_reference = values.get('payment_reference', application.payment_reference).strip()
            if next_status in ('payment_processing', 'paid') and application.program.funding_status != 'funded':
                return Response(
                    {'status': 'The programme must be marked funded before payment can be processed.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if next_status == 'declined' and not reason:
                return Response(
                    {'admin_reason': 'Provide the reason for declining this application.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if next_status == 'paid' and not payment_reference:
                return Response(
                    {'payment_reference': 'Record the payment reference before confirming payment.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            changed = (
                next_status != application.status
                or reason != application.admin_reason
                or payment_reference != application.payment_reference
            )
            if changed:
                old_status = application.status
                application.status = next_status
                application.admin_reason = reason
                application.payment_reference = payment_reference
                application.reviewed_by = request.user
                if next_status == 'paid' and old_status != 'paid':
                    application.payment_confirmed_by = request.user
                    application.payment_confirmed_at = timezone.now()
                try:
                    with transaction.atomic():
                        application.save(update_fields=(
                            'status', 'admin_reason', 'payment_reference', 'reviewed_by',
                            'payment_confirmed_by', 'payment_confirmed_at', 'updated_at',
                        ))
                except IntegrityError:
                    return Response(
                        {'payment_reference': 'This payment reference is already recorded for another application.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                SupportApplicationEvent.objects.create(
                    application=application,
                    actor=request.user,
                    status=application.status,
                    reason=application.admin_reason,
                    payment_reference=application.payment_reference,
                )

        return Response(SupportApplicationSerializer(application).data)
