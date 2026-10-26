from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
import uuid
from apps.accounts.models import User
from .private_storage import vendor_verification_storage


class VendorProfile(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]

    CATEGORY_CHOICES = [
        ('education', 'Education'),
        ('technology', 'Technology'),
        ('health', 'Health'),
        ('finance', 'Finance'),
        ('engineering', 'Engineering'),
        ('media', 'Media and arts'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vendor_profile',
    )
    business_name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=24, choices=CATEGORY_CHOICES)
    contact_name = models.CharField(max_length=150)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=32)
    website = models.URLField(blank=True)
    location = models.CharField(max_length=200)
    logo = models.ImageField(upload_to='vendors/logos/%Y/%m/', blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)
    admin_feedback = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_vendor_profiles',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_profiles'
        indexes = [models.Index(fields=['status', 'created_at'])]


class VendorVerification(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='verifications')
    document_type = models.CharField(max_length=64)
    document = models.FileField(
        upload_to='vendors/verification/%Y/%m/',
        storage=vendor_verification_storage,
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)
    admin_feedback = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_vendor_verifications',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'vendor_verifications'
        ordering = ['-created_at']


class SponsorshipCampaign(models.Model):
    TYPE_CHOICES = [
        ('tutorial', 'Tutorial sponsorship'),
        ('study_area', 'Study area sponsorship'),
        ('learning_initiative', 'Learning initiative'),
        ('contest', 'Contest sponsorship'),
        ('support_program', 'Support programme'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending approval'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('cancellation_requested', 'Cancellation requested'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('changes_requested', 'Changes requested'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=200)
    objectives = models.TextField()
    target_audience = models.CharField(max_length=500)
    eligibility_rules = models.JSONField(default=dict, blank=True)
    campaign_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    study_area = models.CharField(max_length=40, blank=True)
    target_content_ids = models.JSONField(default=list, blank=True)
    description = models.TextField()
    sponsor_disclosure = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    target_views = models.PositiveIntegerField(null=True, blank=True)
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    approved_budget_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='KES')
    budget_tracking_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=28, choices=STATUS_CHOICES, default='draft', db_index=True)
    admin_feedback = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_sponsorship_campaigns',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sponsorship_campaigns'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'status', 'created_at']),
            models.Index(fields=['status', 'start_date', 'end_date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F('start_date')),
                name='campaign_end_date_not_before_start',
            ),
            models.CheckConstraint(
                condition=Q(budget_amount__isnull=True) | Q(budget_amount__gte=0),
                name='campaign_budget_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(approved_budget_amount__isnull=True) | Q(approved_budget_amount__gte=0),
                name='campaign_approved_budget_nonnegative',
            ),
        ]

    def sync_completion_status(self):
        if self.status == 'active' and self.end_date < timezone.localdate():
            self.status = 'completed'
            self.save(update_fields=['status', 'updated_at'])


class CampaignAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(SponsorshipCampaign, on_delete=models.CASCADE, related_name='assets')
    file = models.FileField(upload_to='campaigns/assets/%Y/%m/')
    description = models.CharField(max_length=300, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='campaign_assets',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'campaign_assets'


class CampaignApproval(models.Model):
    DECISION_CHOICES = [
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('changes_requested', 'Changes requested'),
        ('paused', 'Paused'),
        ('resumed', 'Resumed'),
        ('cancellation_requested', 'Cancellation requested'),
        ('cancellation_approved', 'Cancellation approved'),
        ('cancellation_denied', 'Cancellation denied'),
        ('activated', 'Activated'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(SponsorshipCampaign, on_delete=models.CASCADE, related_name='review_history')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='campaign_review_actions',
    )
    decision = models.CharField(max_length=32, choices=DECISION_CHOICES)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'campaign_approvals'
        ordering = ['-created_at']


class CampaignEvent(models.Model):
    EVENT_CHOICES = [
        ('view', 'View'),
        ('click', 'Click'),
        ('lesson_start', 'Lesson start'),
        ('lesson_completion', 'Lesson completion'),
        ('assessment_completion', 'Assessment completion'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(SponsorshipCampaign, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='campaign_events',
    )
    deduplication_key = models.CharField(max_length=160)
    source = models.CharField(max_length=32, default='platform')
    occurred_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'campaign_events'
        indexes = [models.Index(fields=['campaign', 'event_type', 'occurred_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'deduplication_key'],
                name='unique_campaign_event_deduplication_key',
            ),
        ]


class VendorJob(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('open', 'Open'), ('matched', 'Matched'),
        ('in_progress', 'In Progress'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posted_jobs')
    title = models.CharField(max_length=200)
    description = models.TextField()
    profession_required = models.CharField(max_length=100, db_index=True)
    skills_required = models.JSONField(default=list)
    budget_min = models.DecimalField(max_digits=12, decimal_places=2)
    budget_max = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=5, default='KES')
    deadline = models.DateField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    min_trust_score = models.FloatField(default=50.0)
    evidence_urls = models.JSONField(default=list)
    location_preference = models.CharField(max_length=200, blank=True)
    assigned_professional = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_jobs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_jobs'
        indexes = [models.Index(fields=['profession_required', 'status'])]


class VendorRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_given')
    professional = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vendor_ratings')
    job = models.OneToOneField(VendorJob, on_delete=models.CASCADE, related_name='rating')
    quality_score = models.PositiveSmallIntegerField()
    communication_score = models.PositiveSmallIntegerField()
    timeliness_score = models.PositiveSmallIntegerField()
    overall_score = models.FloatField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'vendor_ratings'
