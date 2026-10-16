import re
from datetime import date
from decimal import Decimal, InvalidOperation

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
    SponsoredViewAttempt,
    SupportApplication,
    SupportEligibility,
    SupportApplicationEvent,
    SupportProgram,
    TutorialProgress,
)

MAIN_CONTEST_MERIT_PROGRAM_TYPES = frozenset({'opportunity', 'philanthropic_support'})


class SupportApplicationInputSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    registered_phone_number = serializers.CharField(max_length=20)
    mpesa_number = serializers.CharField(max_length=20)
    application_data = serializers.DictField(
        child=serializers.CharField(allow_blank=True, trim_whitespace=True),
        required=False,
        default=dict,
    )

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
            'application_fields_at_application', 'application_data',
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


class SupportApplicationInformationSerializer(serializers.Serializer):
    mpesa_number = serializers.CharField(max_length=20, required=False)
    application_data = serializers.DictField(
        child=serializers.CharField(allow_blank=True, trim_whitespace=True),
        required=False,
    )

    def validate(self, attrs):
        if not attrs or (
            set(attrs) == {'application_data'}
            and not attrs['application_data']
        ):
            raise serializers.ValidationError('Submit at least one requested field.')
        return attrs

    def validate_mpesa_number(self, value):
        value = re.sub(r'[\s-]', '', value)
        if not re.fullmatch(r'(?:\+?254|0)\d{9}', value):
            raise serializers.ValidationError('Enter a valid Kenyan M-Pesa number.')
        return value


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


def get_program_eligibility_rule(program):
    config = program.eligibility_config or {}
    if config:
        labels = {
            'main_contest_average': 'verified Main Contest average',
            'sponsored_view_average': 'verified Sponsored View average',
            'tutorial_completed_count': 'completed Tutorials',
        }
        source = config['source']
        return {
            'source': source,
            'minimum_score': float(config['minimum_score']),
            'minimum_attempts': config.get('minimum_attempts', 1),
            'label': labels[source],
        }
    if program.program_type in MAIN_CONTEST_MERIT_PROGRAM_TYPES:
        return {
            'source': 'main_contest_average',
            'minimum_score': float(program.merit_cutoff),
            'minimum_attempts': 1,
            'label': 'verified Main Contest average',
        }
    return None


def get_program_eligibility_metric(user, rule):
    if rule['source'] == 'main_contest_average':
        average, count, tutorial_weeks = get_support_merit(user)
        return average, count, tutorial_weeks
    if rule['source'] == 'sponsored_view_average':
        scores = SponsoredViewAttempt.objects.filter(
            user=user,
            status='graded',
            score__isnull=False,
            payment__status='verified',
        ).aggregate(average=Avg('score'), count=Count('id'))
        return round(scores['average'] or 0, 2), scores['count'], 0
    completed = TutorialProgress.objects.filter(
        user=user,
        completed_at__isnull=False,
    ).count()
    return completed, completed, 0


def validate_application_data(fields, data):
    if not isinstance(data, dict):
        raise serializers.ValidationError({'application_data': 'Provide an object of programme-specific answers.'})
    allowed = {field['key'] for field in fields}
    unknown = set(data) - allowed
    if unknown:
        raise serializers.ValidationError({
            'application_data': f'Unsupported programme-specific field(s): {", ".join(sorted(unknown))}.',
        })
    cleaned = {}
    errors = {}
    for field in fields:
        key = field['key']
        value = data.get(key, '').strip()
        if field.get('required', True) and not value:
            errors[key] = f'{field["label"]} is required.'
            continue
        if not value:
            continue
        if len(value) > field.get('max_length', 500):
            errors[key] = f'{field["label"]} exceeds the maximum length.'
        elif field.get('type', 'text') == 'select' and value not in field['options']:
            errors[key] = f'Select one of the published options for {field["label"]}.'
        elif field.get('type') == 'number':
            try:
                parsed_number = Decimal(value)
                if not parsed_number.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                errors[key] = f'{field["label"]} must be a number.'
        elif field.get('type') == 'date':
            try:
                date.fromisoformat(value)
            except ValueError:
                errors[key] = f'{field["label"]} must be a valid ISO date.'
        cleaned[key] = value
    if errors:
        raise serializers.ValidationError({'application_data': errors})
    return cleaned


@transaction.atomic
def sync_support_eligibility(user, program, *, merit_score=None, completed_contests=None, tutorial_weeks=None):
    rule = get_program_eligibility_rule(program)
    if rule:
        metric_score, metric_count, tutorial_weeks = get_program_eligibility_metric(user, rule)
        cutoff = rule['minimum_score']
    else:
        metric_score, metric_count, tutorial_weeks = get_support_merit(user)
        cutoff = float(program.merit_cutoff)
    qualifies = (
        rule is not None
        and program.funding_status != 'closed'
        and metric_count >= (rule['minimum_attempts'] if rule else 1)
        and metric_score >= cutoff
    )
    eligibility, created = SupportEligibility.objects.select_for_update().get_or_create(
        user=user,
        program=program,
        defaults={
            'merit_score': metric_score,
            'merit_cutoff_at_eligibility': cutoff,
            'completed_contests': metric_count,
            'tutorial_consistency_weeks': tutorial_weeks,
            'eligible': qualifies,
        },
    )
    has_application = SupportApplication.objects.filter(user=user, program=program).exists()
    was_eligible = eligibility.eligible
    previous_cutoff = eligibility.merit_cutoff_at_eligibility
    eligibility.merit_score = metric_score
    eligibility.merit_cutoff_at_eligibility = cutoff
    eligibility.completed_contests = metric_count
    eligibility.tutorial_consistency_weeks = tutorial_weeks
    eligibility.eligible = qualifies or has_application
    criteria_changed = not created and previous_cutoff != cutoff
    should_notify = qualifies and (created or not was_eligible or criteria_changed) and not has_application
    if should_notify:
        send_notification(
            user=user,
            notification_type='opportunity',
            title=(
                'Eligibility criteria updated'
                if criteria_changed and was_eligible
                else 'You are eligible to apply'
            ),
            message=(
                f'Your verified {rule["label"]} meets the published criteria for {program.title}. '
                'Submit the private application and payment details form for review.'
            ),
            action_url='/opportunities',
            metadata={'program_id': str(program.id), 'program_type': program.program_type},
        )
        eligibility.notified_at = timezone.now()
    elif was_eligible and not qualifies and not has_application:
        send_notification(
            user=user,
            notification_type='opportunity',
            title='Opportunity eligibility changed',
            message=(
                f'Your eligibility for {program.title} has changed because your verified '
                'results no longer meet the published criteria. Review the current rules and your next steps.'
            ),
            action_url='/opportunities',
            metadata={
                'program_id': str(program.id),
                'program_type': program.program_type,
                'eligible': False,
            },
        )
    eligibility.save(update_fields=(
        'merit_score', 'merit_cutoff_at_eligibility', 'completed_contests', 'tutorial_consistency_weeks',
        'eligible', 'notified_at', 'updated_at',
    ))
    return eligibility, metric_score, metric_count, tutorial_weeks


def reconcile_support_program(program_id):
    program = SupportProgram.objects.get(id=program_id)
    if program.status != 'published' or (program.deadline and program.deadline <= timezone.now()):
        eligible_records = SupportEligibility.objects.filter(
            program=program,
            eligible=True,
        ).exclude(applications__isnull=False).select_related('user')
        for eligibility in eligible_records:
            eligibility.eligible = False
            eligibility.save(update_fields=('eligible', 'updated_at'))
            send_notification(
                user=eligibility.user,
                notification_type='opportunity',
                title='Opportunity eligibility changed',
                message=(
                    f'Eligibility for {program.title} is no longer available because the '
                    'published programme status or deadline changed. Review the programme details.'
                ),
                action_url='/opportunities',
                metadata={
                    'program_id': str(program.id),
                    'program_type': program.program_type,
                    'eligible': False,
                },
            )
        return

    users = User.objects.filter(
        Q(assessment_attempts__status='graded', assessment_attempts__score__isnull=False, assessment_attempts__is_flagged=False)
        | Q(sponsored_view_attempts__status='graded', sponsored_view_attempts__score__isnull=False)
        | Q(tutorial_progress__completed_at__isnull=False)
    ).distinct()
    for user in users.iterator():
        sync_support_eligibility(user, program)


def sync_support_eligibilities_for_user(user):
    now = timezone.now()
    programs = SupportProgram.objects.filter(status='published').filter(
        Q(deadline__isnull=True) | Q(deadline__gt=now),
    )
    for program in programs:
        sync_support_eligibility(user, program)


class SupportProgramListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        now = timezone.now()
        programs = SupportProgram.objects.filter(
            status='published',
        ).filter(
            Q(deadline__isnull=True) | Q(deadline__gt=now),
        ).order_by('deadline', 'title')
        applications = {
            application.program_id: application
            for application in SupportApplication.objects.filter(
                user=request.user,
                program__in=programs,
            ).select_related('program').prefetch_related('events')
        }
        results = []
        for program in programs:
            eligibility, metric_score, metric_count, tutorial_weeks = sync_support_eligibility(
                request.user, program,
            )
            rule = get_program_eligibility_rule(program)
            application = applications.get(program.id)
            if not rule:
                eligibility_reason = (
                    'An administrator must configure and publish eligibility criteria for this '
                    'programme type before eligibility can be evaluated.'
                )
            elif program.funding_status == 'closed':
                eligibility_reason = 'Funding for this programme is closed.'
            elif metric_count < rule['minimum_attempts']:
                eligibility_reason = (
                    f'Complete at least {rule["minimum_attempts"]} verified '
                    f'{rule["label"]} result(s); {metric_count} currently qualify.'
                )
            elif metric_score < rule['minimum_score']:
                eligibility_reason = (
                    f'Your verified {rule["label"]} is {metric_score}; the published minimum is '
                    f'{rule["minimum_score"]}.'
                )
            else:
                eligibility_reason = (
                    f'Eligible: verified {rule["label"]} is {metric_score}, meeting the '
                    f'published minimum of {rule["minimum_score"]}.'
                )
            results.append({
                'id': str(program.id),
                'title': program.title,
                'description': program.description,
                'program_type': program.program_type,
                'eligibility_rules': program.eligibility_rules,
                'merit_cutoff': rule['minimum_score'] if rule else None,
                'funding_status': program.funding_status,
                'deadline': program.deadline,
                'eligibility_source': rule['source'] if rule else None,
                'metric_label': rule['label'] if rule else None,
                'merit_score': metric_score,
                'completed_contests': metric_count,
                'completed_requirements': metric_count,
                'minimum_attempts': rule['minimum_attempts'] if rule else None,
                'tutorial_consistency_weeks': tutorial_weeks,
                'eligible': eligibility.eligible,
                'eligibility_reason': eligibility_reason,
                'application_fields': program.application_fields,
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


class SupportApplicationInformationView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, application_id):
        serializer = SupportApplicationInformationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            application = get_object_or_404(
                SupportApplication.objects.select_for_update(),
                id=application_id,
                user=request.user,
                status='awaiting_information',
            )
            values = serializer.validated_data
            if 'mpesa_number' in values:
                application.mpesa_number = values['mpesa_number']
            if 'application_data' in values:
                merged_data = {
                    **application.application_data,
                    **values['application_data'],
                }
                application.application_data = validate_application_data(
                    application.application_fields_at_application,
                    merged_data,
                )
            application.status = 'submitted'
            application.admin_reason = ''
            application.save(update_fields=(
                'mpesa_number', 'application_data', 'status', 'admin_reason', 'updated_at',
            ))
            SupportApplicationEvent.objects.create(
                application=application,
                actor=request.user,
                status=application.status,
                reason='Applicant submitted the requested information.',
            )
        return Response(SupportApplicationSerializer(application).data)


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
            if not eligibility.eligible:
                return Response(
                    {'error': 'This programme is available only to students who meet its published eligibility criteria.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                application_data = validate_application_data(
                    program.application_fields,
                    values.get('application_data', {}),
                )
            except serializers.ValidationError as error:
                return Response(error.detail, status=status.HTTP_400_BAD_REQUEST)

            try:
                with transaction.atomic():
                    application = SupportApplication.objects.create(
                        user=request.user,
                        program=program,
                        eligibility=eligibility,
                        program_title_at_application=program.title,
                        program_type_at_application=program.program_type,
                        eligibility_rules_at_application=program.eligibility_rules,
                        merit_cutoff_at_application=eligibility.merit_cutoff_at_eligibility,
                        full_name=registered_name,
                        registered_phone_number=registered_phone,
                        mpesa_number=values['mpesa_number'],
                        merit_score_at_application=merit_score,
                        tutorial_consistency_weeks_at_application=tutorial_weeks,
                        application_fields_at_application=program.application_fields,
                        application_data=application_data,
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
            'submitted': {'under_review', 'awaiting_information', 'declined'},
            'under_review': {'approved', 'awaiting_funding', 'awaiting_information', 'declined'},
            'approved': {'awaiting_funding', 'payment_processing', 'declined'},
            'awaiting_funding': {'payment_processing', 'declined'},
            'payment_processing': {'paid', 'declined'},
            'awaiting_information': {'under_review', 'declined'},
            'paid': set(),
            'declined': set(),
        }

        notification_payload = None
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
                notification_payload = (
                    application.user,
                    application.program_title_at_application,
                    application.status,
                    application.admin_reason,
                )

        if notification_payload:
            student, program_title, application_status, reason = notification_payload
            send_notification(
                user=student,
                notification_type='opportunity',
                title='Opportunity application updated',
                message=(
                    f'{program_title}: your application is now '
                    f'{application_status.replace("_", " ")}.'
                    + (f' {reason}' if reason else '')
                ),
                action_url='/opportunities',
                metadata={
                    'application_id': str(application.id),
                    'program_id': str(application.program_id),
                    'status': application_status,
                },
            )
        return Response(SupportApplicationSerializer(application).data)
