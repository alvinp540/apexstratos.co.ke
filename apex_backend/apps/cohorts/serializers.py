from rest_framework import serializers
from .models import (
    Cohort, Assessment, Question, AssessmentAttempt, CohortEnrollment,
    PSPRegistration, PSPVerification, WhatsAppInviteRequest, CohortCoachAssignment,
    Tutorial, TutorialQuestion,
    AssessmentSchedule, AssessmentScheduleQuestion, ParticipationPayment, AssessmentScheduleAttempt
)


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ('id', 'question_type', 'text', 'options', 'points', 'order')


class TutorialQuestionPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = TutorialQuestion
        fields = ('id', 'order', 'question_type', 'prompt', 'options')
        read_only_fields = fields


class TutorialSerializer(serializers.ModelSerializer):
    questions = TutorialQuestionPublicSerializer(many=True, read_only=True)
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Tutorial
        fields = (
            'id', 'month', 'week', 'day', 'daily_slot', 'field', 'title',
            'description', 'learning_objectives', 'concept_explanation',
            'terminology_and_components', 'why_it_matters', 'how_it_works',
            'worked_examples', 'common_mistakes', 'practical_application',
            'decisions_and_tradeoffs', 'related_concepts',
            'difficulty', 'video_url', 'duration_minutes',
            'related_assessment_ids', 'scheduled_for', 'questions',
        )
        read_only_fields = fields

    def get_video_url(self, obj):
        return obj.video.url if obj.video else None


class TutorialQuerySerializer(serializers.Serializer):
    month = serializers.IntegerField(required=False, min_value=1)
    week = serializers.IntegerField(required=False, min_value=1, max_value=4)
    day = serializers.IntegerField(required=False, min_value=0, max_value=3)
    field = serializers.ChoiceField(required=False, choices=Tutorial.FIELD_CHOICES)


class AssessmentSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Assessment
        fields = (
            'id', 'title', 'instructions', 'video_url', 'time_limit_minutes',
            'difficulty', 'passing_score', 'is_active', 'questions',
        )


class CohortSerializer(serializers.ModelSerializer):
    participant_count = serializers.SerializerMethodField()
    default_assessment_id = serializers.SerializerMethodField()
    duration_days = serializers.SerializerMethodField()

    class Meta:
        model = Cohort
        fields = (
            'id', 'title', 'profession', 'level', 'payment_tier', 'description', 'start_date',
            'end_date', 'max_participants', 'assessment_unlock_threshold', 'status',
            'participant_count', 'skills_coach_payout', 'consistency_coach_payout',
            'improvement_coach_payout', 'account_based_marketing_budget', 'created_at',
            'default_assessment_id', 'duration_days',
        )

    def get_participant_count(self, obj):
        return obj.enrollments.count()

    def get_default_assessment_id(self, obj):
        assessment = obj.assessments.filter(is_active=True).order_by('created_at').first()
        return str(assessment.id) if assessment else None

    def get_duration_days(self, obj):
        return max(1, (obj.end_date - obj.start_date).days)


class AssessmentAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentAttempt
        fields = (
            'id', 'assessment', 'cohort', 'score', 'status', 'question_order',
            'video_watched_seconds', 'video_completed', 'started_at', 'submitted_at', 'is_flagged',
        )
        read_only_fields = fields


class HeartbeatSerializer(serializers.Serializer):
    tab_switch = serializers.BooleanField(default=False)
    time_anomaly = serializers.BooleanField(default=False)
    video_watched_seconds = serializers.IntegerField(required=False, min_value=0)
    video_completed = serializers.BooleanField(default=False)


class PSPVerificationSerializer(serializers.ModelSerializer):
    verified_by = serializers.SerializerMethodField()

    class Meta:
        model = PSPVerification
        fields = ('id', 'registration', 'verified_by', 'amount_received', 'payment_reference', 'notes', 'verified_at')

    def get_verified_by(self, obj):
        if obj.verified_by:
            return {'id': str(obj.verified_by.id), 'email': obj.verified_by.email, 'username': obj.verified_by.username}
        return None


class PSPRegistrationSerializer(serializers.ModelSerializer):
    verifications = PSPVerificationSerializer(many=True, read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = PSPRegistration
        fields = (
            'id', 'user', 'full_name', 'phone_number', 'psp_tier', 'cohort', 'amount_expected', 'status', 'created_at', 'verifications'
        )
    payment_till_number = serializers.SerializerMethodField()

    def get_payment_till_number(self, obj):
        return PSPRegistration.PAYMENT_TILL_NUMBER

    def get_user(self, obj):
        return {'id': str(obj.user.id), 'email': obj.user.email, 'username': obj.user.username}


class PSPRegistrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PSPRegistration
        fields = ('full_name', 'phone_number', 'psp_tier', 'cohort')

    def validate(self, attrs):
        attrs['amount_expected'] = PSPRegistration.PSP_TIER_AMOUNTS[attrs['psp_tier']]
        user = self.context['request'].user
        cohort = attrs.get('cohort')
        if cohort and cohort.payment_tier != attrs['psp_tier']:
            raise serializers.ValidationError({'cohort': 'This cohort is for a different payment tier.'})
        if not cohort:
            from .placement import choose_cohort_for_tier
            cohort = choose_cohort_for_tier(attrs['psp_tier'])
            if not cohort:
                raise serializers.ValidationError({'cohort': 'No open placement is available for this payment tier yet.'})
            attrs['cohort'] = cohort
        if PSPRegistration.objects.filter(
            user=user,
            cohort=attrs.get('cohort'),
            psp_tier=attrs['psp_tier'],
        ).exists():
            raise serializers.ValidationError('You already have this PSP registration.')
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        return PSPRegistration.objects.create(user=request.user, **validated_data)


class WhatsAppInviteRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppInviteRequest
        fields = ('id', 'cohort', 'coach_type', 'status', 'group_link', 'admin_notes', 'created_at', 'reviewed_at')
        read_only_fields = ('id', 'status', 'group_link', 'admin_notes', 'created_at', 'reviewed_at')


class CoachPayoutSerializer(serializers.ModelSerializer):
    cohort_title = serializers.CharField(source='cohort.title', read_only=True)
    role_label = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = CohortCoachAssignment
        fields = (
            'id', 'cohort', 'cohort_title', 'role', 'role_label', 'score', 'payout_amount',
            'payment_method', 'payment_recipient', 'payment_note', 'payout_status',
            'payment_details_submitted_at', 'allocated_at', 'eligibility_status',
            'eligibility_reason', 'improvement_delta', 'follow_up_completed',
            'deployment_eligible',
        )
        read_only_fields = (
            'id', 'cohort', 'cohort_title', 'role', 'role_label', 'score', 'payout_amount',
            'payout_status', 'payment_details_submitted_at', 'allocated_at',
            'eligibility_status', 'eligibility_reason', 'improvement_delta',
            'follow_up_completed', 'deployment_eligible',
        )

    def validate(self, attrs):
        if self.instance and self.instance.payout_status == 'paid':
            raise serializers.ValidationError('Payment details cannot be changed after payout is marked paid.')
        method = attrs.get('payment_method', getattr(self.instance, 'payment_method', ''))
        recipient = attrs.get('payment_recipient', getattr(self.instance, 'payment_recipient', '')).strip()
        if not method:
            raise serializers.ValidationError({'payment_method': 'Choose a payment method.'})
        if not recipient:
            raise serializers.ValidationError({'payment_recipient': 'Enter the number or account to receive payment.'})
        return attrs


class AssessmentScheduleQuestionPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentScheduleQuestion
        fields = ('id', 'order', 'question_type', 'prompt', 'options')
        read_only_fields = fields


class AssessmentScheduleSerializer(serializers.ModelSerializer):
    questions = AssessmentScheduleQuestionPublicSerializer(many=True, read_only=True)
    video_url = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentSchedule
        fields = (
            'id', 'month', 'week', 'day', 'assessment_slot', 'field', 'title',
            'description', 'learning_objectives', 'difficulty', 'video_url',
            'duration_minutes', 'passing_score', 'scheduled_for', 'questions',
            'time_remaining',
        )
        read_only_fields = fields

    def get_video_url(self, obj):
        return obj.video.url if obj.video else None

    def get_time_remaining(self, obj):
        return obj.duration_minutes * 60


class AssessmentScheduleAttemptSerializer(serializers.ModelSerializer):
    assessment_title = serializers.CharField(source='assessment.title', read_only=True)
    time_remaining = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentScheduleAttempt
        fields = (
            'id', 'user', 'assessment', 'assessment_title', 'status', 'score',
            'video_watched_seconds', 'video_completed', 'started_at', 'submitted_at',
            'duration_seconds', 'deadline_at', 'time_remaining', 'is_expired', 'is_flagged',
        )
        read_only_fields = (
            'id', 'user', 'assessment', 'status', 'score', 'started_at',
            'submitted_at', 'deadline_at', 'is_flagged',
        )

    def get_time_remaining(self, obj):
        from django.utils import timezone
        deadline = obj.deadline_at or (
            obj.started_at + timezone.timedelta(seconds=obj.duration_seconds)
        )
        return max(0, int((deadline - timezone.now()).total_seconds()))

    def get_is_expired(self, obj):
        return obj.is_time_expired


class ParticipationPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParticipationPayment
        fields = (
            'id', 'user', 'full_name', 'phone_number', 'field', 'amount_kes',
            'till_number', 'status', 'payment_reference', 'mpesa_transaction_id',
            'verification_notes', 'rejection_reason', 'created_at', 'verified_at',
            'expires_at', 'verified_by',
        )
        read_only_fields = fields
