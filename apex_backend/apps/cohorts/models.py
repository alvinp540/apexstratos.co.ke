from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
import re
from math import isfinite
from apps.accounts.models import User
from .tutorial_schedule import CAPABILITY_FIELDS


class Cohort(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('in_progress', 'In Progress'), ('closed', 'Closed')]
    LEVEL_CHOICES = [('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')]
    PAYMENT_TIER_CHOICES = [
        ('10kes', 'KES 10'),
        ('100kes', 'KES 100'),
        ('1000kes', 'KES 1,000'),
    ]
    ASSESSMENT_UNLOCK_CHOICES = [
        (20, '20 participants'),
        (50, '50 participants'),
        (100, '100 participants'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    profession = models.CharField(max_length=100, db_index=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='beginner', db_index=True)
    payment_tier = models.CharField(max_length=10, choices=PAYMENT_TIER_CHOICES, db_index=True, default='100kes')
    description = models.TextField(blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    max_participants = models.PositiveIntegerField(default=100)
    assessment_unlock_threshold = models.PositiveIntegerField(
        choices=ASSESSMENT_UNLOCK_CHOICES,
        default=20,
        help_text='Minimum verified participants required before assessments can start.',
    )
    skills_coach_payout = models.DecimalField(max_digits=10, decimal_places=2, default=500)
    consistency_coach_payout = models.DecimalField(max_digits=10, decimal_places=2, default=300)
    improvement_coach_payout = models.DecimalField(max_digits=10, decimal_places=2, default=300)
    account_based_marketing_budget = models.DecimalField(max_digits=10, decimal_places=2, default=300)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cohorts'


class Assessment(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard'), ('expert', 'Expert')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='assessments')
    title = models.CharField(max_length=200)
    instructions = models.TextField()
    video_url = models.URLField(blank=True, help_text='Video source for this assessment.')
    time_limit_minutes = models.PositiveIntegerField(default=30)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    passing_score = models.FloatField(default=70.0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assessments'


class Question(models.Model):
    QUESTION_TYPE = [
        ('mcq', 'Multiple Choice'), ('scenario', 'Scenario'), ('true_false', 'True/False')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE, default='mcq')
    text = models.TextField()
    options = models.JSONField(default=list)
    correct_answer = models.CharField(max_length=10)
    points = models.PositiveSmallIntegerField(default=1)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'questions'
        ordering = ['order']


class Tutorial(models.Model):
    FIELD_CHOICES = [(field, field) for field in CAPABILITY_FIELDS]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_review', 'In Review'),
        ('approved', 'Approved'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    DIFFICULTY_CHOICES = [
        ('foundation', 'Foundation'),
        ('developing', 'Developing'),
        ('integrated', 'Integrated'),
    ]
    WEEKDAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
    ]
    DAILY_SLOT_CHOICES = [(1, 'Tutorial 1'), (2, 'Tutorial 2')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    week = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)])
    day = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    daily_slot = models.PositiveSmallIntegerField(choices=DAILY_SLOT_CHOICES)
    field = models.CharField(max_length=40, choices=FIELD_CHOICES, db_index=True)
    title = models.CharField(max_length=240)
    description = models.TextField()
    imported_external_id = models.CharField(max_length=120, blank=True, db_index=True)
    content_source = models.CharField(max_length=500, blank=True)
    content_license = models.CharField(max_length=120, blank=True)
    content_attribution = models.TextField(blank=True)
    learning_objectives = models.JSONField(default=list)
    concept_explanation = models.TextField(blank=True)
    terminology_and_components = models.TextField(blank=True)
    why_it_matters = models.TextField(blank=True)
    how_it_works = models.TextField(blank=True)
    worked_examples = models.TextField(blank=True)
    common_mistakes = models.TextField(blank=True)
    practical_application = models.TextField(blank=True)
    decisions_and_tradeoffs = models.TextField(blank=True)
    related_concepts = models.TextField(blank=True)
    difficulty = models.CharField(max_length=16, choices=DIFFICULTY_CHOICES, default='foundation')
    video = models.FileField(upload_to='tutorials/videos/%Y/%m/', blank=True)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    related_assessment_ids = models.JSONField(default=list, blank=True)
    scheduled_for = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft', db_index=True)
    expert_reviewed = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_tutorials')
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_tutorials')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tutorials'
        ordering = ['month', 'week', 'day', 'daily_slot', 'field']
        constraints = [
            models.UniqueConstraint(
                fields=['month', 'week', 'day', 'daily_slot', 'field'],
                name='unique_tutorial_schedule_slot',
            ),
        ]
        indexes = [
            models.Index(fields=['field', 'month', 'week', 'day']),
            models.Index(fields=['status', 'scheduled_for']),
        ]

    def validate_for_publication(self):
        errors = {}
        teaching_sections = (
            'concept_explanation', 'terminology_and_components', 'why_it_matters',
            'how_it_works', 'worked_examples', 'common_mistakes',
            'practical_application', 'decisions_and_tradeoffs', 'related_concepts',
        )
        missing_sections = [name for name in teaching_sections if not getattr(self, name).strip()]
        if missing_sections:
            errors['teaching_content'] = 'Complete all teaching sections: ' + ', '.join(missing_sections)
        if not isinstance(self.learning_objectives, list) or len(self.learning_objectives) < 3:
            errors['learning_objectives'] = 'Add at least three learning objectives.'
        questions = list(self.questions.order_by('order'))
        if [question.order for question in questions] != list(range(1, 11)):
            errors['questions'] = 'A tutorial must have exactly ten questions numbered 1 through 10 before publishing.'
        else:
            for question in questions:
                try:
                    question.full_clean()
                except ValidationError as error:
                    errors[f'question_{question.order}'] = error.messages
                if question.question_type != 'multiple_choice':
                    errors[f'question_{question.order}'] = 'Every published tutorial question must be multiple choice.'
        if self.field in {'Medical and Health', 'Law and Society'} and not self.expert_reviewed:
            errors['expert_reviewed'] = 'Medical and Health and Law and Society tutorials require expert review before publication.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'M{self.month} W{self.week} {self.get_day_display()} / {self.field}: {self.title}'


class TutorialQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', 'Multiple choice'),
        ('scenario', 'Scenario'),
        ('short_answer', 'Short answer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tutorial = models.ForeignKey(Tutorial, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='multiple_choice')
    prompt = models.TextField()
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.TextField()
    rationale = models.TextField(blank=True)
    requires_reasoning = models.BooleanField(default=False)

    class Meta:
        db_table = 'tutorial_questions'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['tutorial', 'order'], name='unique_tutorial_question_order'),
        ]

    def clean(self):
        if self.question_type == 'multiple_choice':
            if not isinstance(self.options, list) or len(self.options) < 2:
                raise ValidationError({'options': 'Multiple-choice questions need at least two options.'})
            if self.correct_answer not in self.options:
                raise ValidationError({'correct_answer': 'The correct answer must match one of the options.'})

    def __str__(self):
        return f'{self.tutorial.title} / Question {self.order}'


class TutorialAttempt(models.Model):
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('graded', 'Graded'),
        ('timed_out', 'Timed Out'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tutorial_attempts')
    tutorial = models.ForeignKey(Tutorial, on_delete=models.PROTECT, related_name='attempts')
    question_snapshot = models.JSONField(default=list)
    answers = models.JSONField(default=dict)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='in_progress', db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tutorial_attempts'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'tutorial'],
                condition=models.Q(status='in_progress'),
                name='one_active_tutorial_attempt',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'tutorial', 'started_at']),
            models.Index(fields=['user', 'status']),
        ]


class TutorialProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tutorial_progress')
    tutorial = models.ForeignKey(Tutorial, on_delete=models.PROTECT, related_name='progress')
    last_attempt = models.ForeignKey(
        TutorialAttempt,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='progress_records',
    )
    best_score = models.FloatField(default=0)
    attempt_count = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tutorial_progress'
        constraints = [
            models.UniqueConstraint(fields=['user', 'tutorial'], name='unique_user_tutorial_progress'),
        ]
        indexes = [
            models.Index(fields=['user', 'completed_at']),
        ]


class CohortEnrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cohort_enrollments'
        unique_together = [['user', 'cohort']]


class AssessmentAttempt(models.Model):
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'), ('submitted', 'Submitted'), ('graded', 'Graded')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attempts')
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='attempts')
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='attempts')
    answers = models.JSONField(default=dict)
    question_order = models.JSONField(default=list)
    video_watched_seconds = models.PositiveIntegerField(default=0)
    video_completed = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    tab_switches = models.PositiveIntegerField(default=0)
    time_anomalies = models.PositiveIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    is_flagged = models.BooleanField(default=False, db_index=True)
    flag_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'assessment_attempts'
        unique_together = [['user', 'assessment']]
        indexes = [models.Index(fields=['user', 'cohort'])]


class PSPRegistration(models.Model):
    PAYMENT_TILL_NUMBER = '1598106'
    PSP_TIER_AMOUNTS = {
        '10kes': 10,
        '100kes': 100,
        '1000kes': 1000,
    }
    PSP_TIER_CHOICES = [
        ('10kes', 'KES 10'),
        ('100kes', 'KES 100'),
        ('1000kes', 'KES 1,000'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('review', 'Payment Review'),
        ('failed', 'Payment Failed'),
        ('confirmed', 'Payment Confirmed'),
        ('active', 'PSP Active'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='psp_registrations')
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=32, db_index=True)
    psp_tier = models.CharField(max_length=64, choices=PSP_TIER_CHOICES)
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='psp_registrations', null=True, blank=True)
    amount_expected = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'psp_registrations'
        unique_together = [['user', 'cohort', 'psp_tier']]


class PSPVerification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(PSPRegistration, on_delete=models.CASCADE, related_name='verifications')
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='psp_verifications')
    amount_received = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True)
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'psp_verifications'


class CohortCoachAssignment(models.Model):
    ROLE_CHOICES = [
        ('skills', 'Skills Coach'),
        ('consistency', 'Consistency Coach'),
        ('improvement', 'Improvement Coach'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('bank_transfer', 'Bank transfer'),
        ('paypal', 'PayPal'),
        ('other', 'Other'),
    ]
    PAYOUT_STATUS_CHOICES = [
        ('awaiting_details', 'Awaiting payment details'),
        ('details_submitted', 'Payment details submitted'),
        ('paid', 'Paid'),
    ]
    ELIGIBILITY_CHOICES = [('valid', 'Valid'), ('invalid', 'Invalid')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='coach_assignments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coach_assignments')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    payout_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=32, choices=PAYMENT_METHOD_CHOICES, blank=True)
    payment_recipient = models.CharField(max_length=255, blank=True)
    payment_note = models.CharField(max_length=255, blank=True)
    payout_status = models.CharField(max_length=32, choices=PAYOUT_STATUS_CHOICES, default='awaiting_details', db_index=True)
    payment_details_submitted_at = models.DateTimeField(null=True, blank=True)
    allocated_at = models.DateTimeField(auto_now_add=True)
    eligibility_status = models.CharField(max_length=12, choices=ELIGIBILITY_CHOICES, default='invalid', db_index=True)
    eligibility_reason = models.CharField(max_length=255, blank=True)
    improvement_delta = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    follow_up_completed = models.BooleanField(default=False)
    deployment_eligible = models.BooleanField(default=False)

    class Meta:
        db_table = 'cohort_coach_assignments'
        constraints = [
            models.UniqueConstraint(fields=['cohort', 'user', 'role'], name='unique_cohort_coach_role'),
        ]


class CohortWalletEntry(models.Model):
    WALLET_CHOICES = [
        ('mentor_payout', 'Mentor Payout'),
        ('account_based_marketing', 'Account-Based Marketing'),
        ('admin', 'Admin Wallet'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='wallet_entries')
    wallet = models.CharField(max_length=32, choices=WALLET_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cohort_wallet_entries')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cohort_wallet_entries'


class WhatsAppInviteRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whatsapp_invite_requests')
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='whatsapp_invite_requests', null=True, blank=True)
    coach_type = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)
    group_link = models.URLField(blank=True)
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_whatsapp_invites')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'whatsapp_invite_requests'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'cohort', 'coach_type'],
                condition=models.Q(status='pending'),
                name='one_pending_whatsapp_invite',
            ),
        ]


class AssessmentSchedule(models.Model):
    """
    Defines the Fri-Sun assessment schedule for each field.
    Friday through Sunday, 3 assessments per day per field.
    Assessments are accessible during the Fri-Sun window but not time-locked to exact days.
    """
    WEEKDAY_CHOICES = [
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    week = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)])
    day = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    assessment_slot = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(3)],
        help_text='Assessment 1, 2, or 3 for the day'
    )
    field = models.CharField(max_length=40, choices=[(f, f) for f in CAPABILITY_FIELDS], db_index=True)
    title = models.CharField(max_length=240)
    description = models.TextField()
    imported_external_id = models.CharField(max_length=120, blank=True, db_index=True)
    content_source = models.CharField(max_length=500, blank=True)
    content_license = models.CharField(max_length=120, blank=True)
    content_attribution = models.TextField(blank=True)
    learning_objectives = models.JSONField(default=list)
    video = models.FileField(upload_to='assessments/videos/%Y/%m/', blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=20)
    difficulty = models.CharField(
        max_length=16,
        choices=[('foundation', 'Foundation'), ('developing', 'Developing'), ('integrated', 'Integrated')],
        default='foundation'
    )
    passing_score = models.FloatField(default=70.0)
    status = models.CharField(
        max_length=16,
        choices=[
            ('draft', 'Draft'),
            ('in_review', 'In Review'),
            ('approved', 'Approved'),
            ('scheduled', 'Scheduled'),
            ('published', 'Published'),
            ('archived', 'Archived'),
        ],
        default='draft',
        db_index=True
    )
    expert_reviewed = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_assessments')
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_assessments')
    scheduled_for = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'assessment_schedules'
        ordering = ['month', 'week', 'day', 'assessment_slot', 'field']
        constraints = [
            models.UniqueConstraint(
                fields=['month', 'week', 'day', 'assessment_slot', 'field'],
                name='unique_assessment_schedule_slot',
            ),
        ]
        indexes = [
            models.Index(fields=['field', 'month', 'week', 'day']),
            models.Index(fields=['status', 'scheduled_for']),
        ]

    def __str__(self):
        day_name = dict(self.WEEKDAY_CHOICES).get(self.day, 'Unknown')
        return f'M{self.month} W{self.week} {day_name} #{self.assessment_slot} / {self.field}: {self.title}'


class AssessmentScheduleQuestion(models.Model):
    """
    Questions for question-first programme assessments.
    Published assessments contain exactly ten ordered multiple-choice questions.
    """
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', 'Multiple choice'),
        ('scenario', 'Scenario'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(AssessmentSchedule, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='multiple_choice')
    prompt = models.TextField()
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.TextField()
    rationale = models.TextField(blank=True)
    requires_reasoning = models.BooleanField(default=False)

    class Meta:
        db_table = 'assessment_schedule_questions'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['assessment', 'order'], name='unique_assessment_question_order'),
        ]

    def clean(self):
        if self.question_type == 'multiple_choice':
            if not isinstance(self.options, list) or len(self.options) < 2:
                raise ValidationError({'options': 'Multiple-choice questions need at least two options.'})
            if self.correct_answer not in self.options:
                raise ValidationError({'correct_answer': 'The correct answer must match one of the options.'})

    def __str__(self):
        return f'{self.assessment.title} / Question {self.order}'


class SponsoredViewAssessment(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    week = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(8)])
    slot = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    field = models.CharField(max_length=40, choices=[(f, f) for f in CAPABILITY_FIELDS], db_index=True)
    title = models.CharField(max_length=240)
    description = models.TextField()
    imported_external_id = models.CharField(max_length=120, blank=True, db_index=True)
    content_source = models.CharField(max_length=500, blank=True)
    content_license = models.CharField(max_length=120, blank=True)
    content_attribution = models.TextField(blank=True)
    learning_objectives = models.JSONField(default=list)
    duration_minutes = models.PositiveSmallIntegerField(default=20)
    difficulty = models.CharField(
        max_length=16,
        choices=[('foundation', 'Foundation'), ('developing', 'Developing'), ('integrated', 'Integrated')],
        default='foundation',
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft', db_index=True)
    expert_reviewed = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_sponsored_assessments')
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_sponsored_assessments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sponsored_view_assessments'
        ordering = ['week', 'field', 'slot']
        constraints = [
            models.UniqueConstraint(fields=['field', 'week', 'slot'], name='unique_sponsored_view_slot'),
        ]

    def __str__(self):
        return f'Week {self.week} / {self.field} #{self.slot}: {self.title}'


class SponsoredViewQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(SponsoredViewAssessment, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    prompt = models.TextField()
    options = models.JSONField(default=list)
    correct_answer = models.TextField()
    rationale = models.TextField()
    requires_reasoning = models.BooleanField(default=False)

    class Meta:
        db_table = 'sponsored_view_questions'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['assessment', 'order'], name='unique_sponsored_view_question_order'),
        ]


class SponsoredViewPayment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sponsored_view_payments')
    assessment = models.ForeignKey(SponsoredViewAssessment, on_delete=models.PROTECT, related_name='payments')
    amount_kes = models.PositiveSmallIntegerField(default=20)
    payment_reference = models.CharField(max_length=255)
    mpesa_transaction_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)
    verification_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_sponsored_view_payments')
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sponsored_view_payments'
        ordering = ['-requested_at']
        constraints = [
            models.UniqueConstraint(fields=['payment_reference'], name='unique_sponsored_view_payment_reference'),
            models.UniqueConstraint(
                fields=['mpesa_transaction_id'],
                condition=~models.Q(mpesa_transaction_id=''),
                name='unique_sponsored_view_transaction',
            ),
            models.CheckConstraint(condition=models.Q(amount_kes=20), name='sponsored_view_price_is_20_kes'),
        ]
        indexes = [
            models.Index(fields=['user', 'status', 'requested_at']),
            models.Index(fields=['assessment', 'status']),
        ]


class SponsoredViewAttempt(models.Model):
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('graded', 'Graded'),
        ('timed_out', 'Timed Out'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.OneToOneField(SponsoredViewPayment, on_delete=models.PROTECT, related_name='attempt')
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sponsored_view_attempts')
    assessment = models.ForeignKey(SponsoredViewAssessment, on_delete=models.PROTECT, related_name='attempts')
    question_snapshot = models.JSONField(default=list)
    answers = models.JSONField(default=dict)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='in_progress', db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    deadline_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sponsored_view_attempts'
        indexes = [
            models.Index(fields=['user', 'started_at']),
            models.Index(fields=['user', 'status']),
        ]


class ParticipationPayment(models.Model):
    """
    Tracks KSh 100 participation payments for accessing assessments.
    Payment is a gating mechanism only; payment does not create merit or improve ranking.
    Separate from escrow, coaching payouts, and subscription tiers.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('under_review', 'Under Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='participation_payments')
    full_name = models.CharField(max_length=200, blank=True)
    phone_number = models.CharField(max_length=32, blank=True)
    field = models.CharField(max_length=40, choices=[(f, f) for f in CAPABILITY_FIELDS], db_index=True)
    amount_kes = models.PositiveIntegerField(default=100)
    till_number = models.CharField(max_length=20, default='1598106')
    payment_reference = models.CharField(max_length=255, blank=True, null=True, unique=True)
    mpesa_transaction_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    verification_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_participation_payments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'participation_payments'
        indexes = [
            models.Index(fields=['user', 'field', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.user.email} / {self.field} / {self.get_status_display()}'


class ParticipationPaymentEvent(models.Model):
    DECISION_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        ParticipationPayment,
        on_delete=models.PROTECT,
        related_name='events',
    )
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='participation_payment_events',
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, db_index=True)
    notes = models.TextField(blank=True)
    confirmed_transaction_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'participation_payment_events'
        ordering = ['created_at']


class AssessmentScheduleAttempt(models.Model):
    """
    Tracks individual attempts on AssessmentSchedule (Fri-Sun CAT) assessments.
    Server-authoritative timer: started_at + duration_seconds determines validity.
    Scoring is server-side only; student API does not expose correct answers or rationales.
    """
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('timed_out', 'Timed Out'),
        ('abandoned', 'Abandoned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assessment_attempts')
    assessment = models.ForeignKey(AssessmentSchedule, on_delete=models.CASCADE, related_name='attempts')
    answers = models.JSONField(default=dict)
    question_order = models.JSONField(default=list)
    assessment_snapshot = models.JSONField(default=dict)
    video_watched_seconds = models.PositiveIntegerField(default=0)
    video_completed = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress', db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=1200)

    tab_switches = models.PositiveIntegerField(default=0)
    time_anomalies = models.PositiveIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    is_flagged = models.BooleanField(default=False, db_index=True)
    flag_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'assessment_schedule_attempts'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'assessment'],
                name='unique_schedule_attempt_per_user',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'assessment']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'started_at']),
        ]

    @property
    def is_time_expired(self):
        """Check the fixed attempt or contest-cycle deadline server-side."""
        from django.utils import timezone
        deadline = self.deadline_at or (
            self.started_at + timezone.timedelta(seconds=self.duration_seconds)
        )
        return timezone.now() >= deadline

    def __str__(self):
        return f'{self.user.email} / {self.assessment.title} / {self.get_status_display()}'


class SupportProgram(models.Model):
    TYPE_CHOICES = [
        ('opportunity', 'Opportunity'),
        ('cash_award', 'Cash award'),
        ('sponsored_view_reward', 'Sponsored View reward'),
        ('philanthropic_support', 'Philanthropic support'),
        ('sponsored_contest_access', 'Sponsored contest access'),
        ('short_term_payout', 'Short-term payout'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('closed', 'Closed'),
    ]
    FUNDING_CHOICES = [
        ('awaiting_funding', 'Awaiting funding'),
        ('funded', 'Funded'),
        ('closed', 'Funding closed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    program_type = models.CharField(max_length=32, choices=TYPE_CHOICES, db_index=True)
    eligibility_rules = models.TextField()
    merit_cutoff = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Cutoff applied to the average of completed, unflagged Main Contest assessment scores.',
    )
    funding_status = models.CharField(max_length=24, choices=FUNDING_CHOICES, default='awaiting_funding')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft', db_index=True)
    deadline = models.DateTimeField(null=True, blank=True)
    eligibility_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Optional explicit rule: {"source": "sponsored_view_average", '
            '"minimum_score": 70, "minimum_attempts": 1}. Leave blank to use '
            'the existing Main Contest rule for opportunity/philanthropic programmes.'
        ),
    )
    application_fields = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Optional list of additional applicant fields. Each item needs key and label; '
            'supports text, textarea, number, date, and select types.'
        ),
    )
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_support_programs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'support_programs'
        ordering = ['deadline', 'title']

    def clean(self):
        super().clean()
        if self.eligibility_config:
            config = self.eligibility_config
            if not isinstance(config, dict) or set(config) - {
                'source', 'minimum_score', 'minimum_attempts',
            }:
                raise ValidationError({
                    'eligibility_config': (
                        'Use source, minimum_score, and optional minimum_attempts only.'
                    ),
                })
            sources = {
                'main_contest_average',
                'sponsored_view_average',
                'tutorial_completed_count',
            }
            source = config.get('source')
            minimum_score = config.get('minimum_score')
            minimum_attempts = config.get('minimum_attempts', 1)
            if source not in sources:
                raise ValidationError({
                    'eligibility_config': 'Select a supported, verified metric source.',
                })
            if (
                isinstance(minimum_score, bool)
                or not isinstance(minimum_score, (int, float))
                or not isfinite(minimum_score)
                or minimum_score < 0
                or (source != 'tutorial_completed_count' and minimum_score > 100)
            ):
                raise ValidationError({
                    'eligibility_config': (
                        'minimum_score must be non-negative and cannot exceed 100 for score metrics.'
                    ),
                })
            if (
                isinstance(minimum_attempts, bool)
                or not isinstance(minimum_attempts, int)
                or minimum_attempts < 1
            ):
                raise ValidationError({
                    'eligibility_config.minimum_attempts': 'Enter a positive integer.',
                })
        elif (
            self.status == 'published'
            and self.program_type not in {'opportunity', 'philanthropic_support'}
        ):
            raise ValidationError({
                'eligibility_config': (
                    'Configure an explicit eligibility rule before publishing this programme type.'
                ),
            })

        if not isinstance(self.application_fields, list) or len(self.application_fields) > 20:
            raise ValidationError({
                'application_fields': 'Provide a list of at most 20 additional application fields.',
            })
        keys = set()
        reserved = {'full_name', 'registered_phone_number', 'mpesa_number'}
        for index, field in enumerate(self.application_fields):
            location = f'application_fields item {index + 1}'
            if not isinstance(field, dict):
                raise ValidationError({'application_fields': f'{location} must be an object.'})
            if set(field) - {'key', 'label', 'type', 'required', 'max_length', 'options'}:
                raise ValidationError({'application_fields': f'{location} has unsupported settings.'})
            key = field.get('key')
            label = field.get('label')
            field_type = field.get('type', 'text')
            required = field.get('required', True)
            max_length = field.get('max_length', 500)
            if (
                not isinstance(key, str)
                or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', key)
                or key in reserved
                or key in keys
            ):
                raise ValidationError({
                    'application_fields': f'{location} needs a unique, non-reserved snake_case key.',
                })
            if not isinstance(label, str) or not label.strip() or len(label) > 120:
                raise ValidationError({'application_fields': f'{location} needs a label of 1–120 characters.'})
            if field_type not in {'text', 'textarea', 'number', 'date', 'select'}:
                raise ValidationError({'application_fields': f'{location} has an unsupported field type.'})
            if not isinstance(required, bool):
                raise ValidationError({'application_fields': f'{location}.required must be true or false.'})
            if (
                isinstance(max_length, bool)
                or not isinstance(max_length, int)
                or not 1 <= max_length <= 5000
            ):
                raise ValidationError({'application_fields': f'{location}.max_length must be 1–5000.'})
            options = field.get('options', [])
            if field_type == 'select' and (
                not isinstance(options, list)
                or len(options) < 2
                or len(options) > 50
                or any(not isinstance(option, str) or not option.strip() for option in options)
                or len({option.strip().casefold() for option in options}) != len(options)
            ):
                raise ValidationError({
                    'application_fields': f'{location} select fields need 2–50 distinct options.',
                })
            if field_type != 'select' and options:
                raise ValidationError({
                    'application_fields': f'{location} only select fields can define options.',
                })
            keys.add(key)

    def __str__(self):
        return self.title


class SupportEligibility(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_eligibilities')
    program = models.ForeignKey(SupportProgram, on_delete=models.PROTECT, related_name='eligibilities')
    merit_score = models.FloatField()
    merit_cutoff_at_eligibility = models.FloatField()
    completed_contests = models.PositiveIntegerField()
    tutorial_consistency_weeks = models.PositiveSmallIntegerField(default=0)
    eligible = models.BooleanField(default=True, db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'support_eligibilities'
        constraints = [
            models.UniqueConstraint(fields=['user', 'program'], name='unique_user_support_eligibility'),
        ]
        indexes = [
            models.Index(fields=['program', 'eligible', '-merit_score']),
        ]


class SupportApplication(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('awaiting_funding', 'Awaiting Funding'),
        ('payment_processing', 'Payment Processing'),
        ('paid', 'Paid'),
        ('declined', 'Declined'),
        ('awaiting_information', 'Awaiting Information'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='support_applications')
    program = models.ForeignKey(SupportProgram, on_delete=models.PROTECT, related_name='applications')
    eligibility = models.ForeignKey(
        SupportEligibility, on_delete=models.PROTECT, related_name='applications'
    )
    program_title_at_application = models.CharField(max_length=200)
    program_type_at_application = models.CharField(max_length=32, choices=SupportProgram.TYPE_CHOICES)
    eligibility_rules_at_application = models.TextField()
    merit_cutoff_at_application = models.FloatField()
    full_name = models.CharField(max_length=200)
    registered_phone_number = models.CharField(max_length=20)
    mpesa_number = models.CharField(max_length=20)
    application_fields_at_application = models.JSONField(default=list, blank=True)
    application_data = models.JSONField(default=dict, blank=True)
    merit_score_at_application = models.FloatField()
    tutorial_consistency_weeks_at_application = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='submitted', db_index=True)
    admin_reason = models.TextField(blank=True)
    payment_reference = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_support_applications'
    )
    payment_confirmed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='confirmed_support_payments'
    )
    payment_confirmed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'support_applications'
        ordering = ['-merit_score_at_application', '-tutorial_consistency_weeks_at_application', 'submitted_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'program'], name='unique_user_support_application'),
            models.UniqueConstraint(
                fields=['payment_reference'],
                condition=~models.Q(payment_reference=''),
                name='unique_support_payment_reference',
            ),
        ]
        indexes = [
            models.Index(fields=['program', 'status', 'submitted_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f'{self.user.email} / {self.program.title} / {self.get_status_display()}'


class SupportApplicationEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        SupportApplication, on_delete=models.PROTECT, related_name='events'
    )
    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='support_application_events'
    )
    status = models.CharField(max_length=24, choices=SupportApplication.STATUS_CHOICES)
    reason = models.TextField(blank=True)
    payment_reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'support_application_events'
        ordering = ['created_at']
