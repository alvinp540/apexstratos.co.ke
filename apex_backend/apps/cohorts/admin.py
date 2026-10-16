from django.contrib import admin
from django.contrib import messages
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import (
	Cohort,
	Assessment,
	Question,
	AssessmentAttempt,
	CohortEnrollment,
	PSPRegistration,
	PSPVerification,
	CohortCoachAssignment,
	CohortWalletEntry,
	WhatsAppInviteRequest,
	Tutorial,
	TutorialQuestion,
	AssessmentSchedule,
	AssessmentScheduleQuestion,
	ParticipationPayment,
	ParticipationPaymentEvent,
	AssessmentScheduleAttempt,
	SupportProgram,
	SupportEligibility,
	SupportApplication,
	SupportApplicationEvent,
	SponsoredViewAssessment,
	SponsoredViewQuestion,
	SponsoredViewPayment,
)
from .allocation import allocate_cohort_rewards
from .support_views import reconcile_support_program
from .sponsored_views import _assessment_ready as _sponsored_assessment_ready


class TutorialQuestionInline(admin.TabularInline):
	model = TutorialQuestion
	extra = 10
	max_num = 10
	fields = ('order', 'question_type', 'prompt', 'options', 'correct_answer', 'rationale', 'requires_reasoning')
	ordering = ('order',)


@admin.register(Tutorial)
class TutorialAdmin(admin.ModelAdmin):
	list_display = ('title', 'field', 'month', 'week', 'day', 'daily_slot', 'status', 'scheduled_for')
	list_filter = ('status', 'field', 'month', 'week', 'day', 'difficulty')
	search_fields = ('title', 'description', 'field')
	readonly_fields = ('status', 'created_by', 'reviewed_by', 'created_at', 'updated_at', 'published_at')
	date_hierarchy = 'scheduled_for'
	inlines = (TutorialQuestionInline,)
	actions = ('submit_for_review', 'approve_content', 'schedule_content', 'publish_content', 'archive_content')
	fieldsets = (
		('Schedule', {'fields': ('month', 'week', 'day', 'daily_slot', 'field', 'scheduled_for')}),
		('Teaching content', {'fields': (
			'title', 'description', 'imported_external_id', 'content_source',
			'content_license', 'content_attribution', 'learning_objectives', 'concept_explanation',
			'terminology_and_components', 'why_it_matters', 'how_it_works',
			'worked_examples', 'common_mistakes', 'practical_application',
			'decisions_and_tradeoffs', 'related_concepts', 'difficulty',
			'duration_minutes', 'related_assessment_ids',
		)}),
		('Review and publication', {'fields': ('status', 'expert_reviewed', 'review_notes', 'created_by', 'reviewed_by', 'published_at')}),
		('Record', {'fields': ('created_at', 'updated_at')}),
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return self.has_module_permission(request)

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)

	def has_delete_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)

	def save_model(self, request, obj, form, change):
		if change:
			obj.status = Tutorial.STATUS_CHOICES[0][0]
			obj.published_at = None
		elif not obj.created_by_id:
			obj.created_by = request.user
			obj.reviewed_by = None
		else:
			obj.created_by = request.user
		super().save_model(request, obj, form, change)

	@admin.action(description='Submit selected tutorials for review')
	def submit_for_review(self, request, queryset):
		self._transition(request, queryset, 'draft', 'in_review', self._validate_review)

	@admin.action(description='Approve selected tutorials')
	def approve_content(self, request, queryset):
		self._transition(request, queryset, 'in_review', 'approved', self._validate_approval, reviewed_by=request.user)

	@admin.action(description='Publish due approved or scheduled tutorials')
	def publish_content(self, request, queryset):
		changed = 0
		for tutorial in queryset:
			if tutorial.status not in ('approved', 'scheduled'):
				self.message_user(request, f'{tutorial.title}: only approved or scheduled tutorials can be published.', level=messages.ERROR)
				continue
			if tutorial.scheduled_for > timezone.now():
				self.message_user(request, f'{tutorial.title}: its scheduled publication time has not arrived.', level=messages.ERROR)
				continue
			try:
				self._validate_publish(tutorial)
			except ValidationError as error:
				self.message_user(request, f'{tutorial.title}: {error.messages}', level=messages.ERROR)
				continue
			tutorial.status = 'published'
			tutorial.published_at = timezone.now()
			tutorial.save(update_fields=['status', 'published_at', 'updated_at'])
			changed += 1
		if changed:
			self.message_user(request, f'{changed} tutorial(s) published.')

	@admin.action(description='Schedule selected approved tutorials')
	def schedule_content(self, request, queryset):
		changed = 0
		for tutorial in queryset:
			if tutorial.status != 'approved' or tutorial.scheduled_for <= timezone.now():
				self.message_user(request, f'{tutorial.title}: choose approved tutorials with a future schedule.', level=messages.ERROR)
				continue
			try:
				self._validate_publish(tutorial)
			except ValidationError as error:
				self.message_user(request, f'{tutorial.title}: {error.messages}', level=messages.ERROR)
				continue
			tutorial.status = 'scheduled'
			tutorial.save(update_fields=['status', 'updated_at'])
			changed += 1
		if changed:
			self.message_user(request, f'{changed} tutorial(s) scheduled.')

	@admin.action(description='Archive selected published tutorials')
	def archive_content(self, request, queryset):
		self._transition(request, queryset, 'published', 'archived')

	def _transition(self, request, queryset, expected_status, new_status, validator=None, **updates):
		changed = 0
		for tutorial in queryset:
			if tutorial.status != expected_status:
				self.message_user(request, f'{tutorial.title}: expected {expected_status}, found {tutorial.status}.', level=messages.ERROR)
				continue
			try:
				if validator:
					validator(tutorial)
			except ValidationError as error:
				self.message_user(request, f'{tutorial.title}: {error.messages}', level=messages.ERROR)
				continue
			for field, value in updates.items():
				setattr(tutorial, field, value)
			tutorial.status = new_status
			tutorial.save(update_fields=['status', 'reviewed_by', 'published_at', 'updated_at'])
			changed += 1
		if changed:
			self.message_user(request, f'{changed} tutorial(s) moved to {new_status}.')

	@staticmethod
	def _validate_review(tutorial):
		teaching_sections = (
			'concept_explanation', 'terminology_and_components', 'why_it_matters',
			'how_it_works', 'worked_examples', 'common_mistakes',
			'practical_application', 'decisions_and_tradeoffs', 'related_concepts',
		)
		if any(not getattr(tutorial, section).strip() for section in teaching_sections):
			raise ValidationError('Complete all structured teaching sections before requesting review.')
		if not isinstance(tutorial.learning_objectives, list) or len(tutorial.learning_objectives) < 3:
			raise ValidationError('At least three learning objectives are required.')
		questions = list(tutorial.questions.order_by('order'))
		if [question.order for question in questions] != list(range(1, 11)):
			raise ValidationError('Exactly ten tutorial questions numbered 1 through 10 are required.')
		for question in questions:
			try:
				question.full_clean()
			except ValidationError as error:
				raise ValidationError(f'Question {question.order}: {error.messages}')
			if question.question_type != 'multiple_choice':
				raise ValidationError(f'Question {question.order} must be multiple choice.')

	@staticmethod
	def _validate_approval(tutorial):
		if tutorial.field in {'Medical and Health', 'Law and Society'} and not tutorial.expert_reviewed:
			raise ValidationError('Mark expert review complete before approving this sensitive-field content.')

	@staticmethod
	def _validate_publish(tutorial):
		tutorial.validate_for_publication()

@admin.action(description='Allocate coach payouts and cohort wallets')
def allocate_rewards(modeladmin, request, queryset):
	for cohort in queryset:
		try:
			result = allocate_cohort_rewards(cohort.id)
			modeladmin.message_user(
				request,
				f"{cohort.title}: allocated {result['coaches']} coaches; admin remainder KES {result['admin_remainder']}",
			)
		except ValueError as exc:
			modeladmin.message_user(request, f'{cohort.title}: {exc}', level='ERROR')


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
	list_display = ('title', 'payment_tier', 'status', 'participant_count', 'assessment_unlock_threshold')
	list_filter = ('payment_tier', 'status', 'assessment_unlock_threshold')
	search_fields = ('title', 'profession')
	actions = (allocate_rewards,)

	def participant_count(self, obj):
		return obj.enrollments.count()


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
	list_display = ('title', 'cohort', 'difficulty', 'time_limit_minutes', 'is_active')
	list_filter = ('is_active', 'difficulty', 'cohort')
	search_fields = ('title', 'cohort__title')
	exclude = ('video_url',)
admin.site.register(Question)
admin.site.register(AssessmentAttempt)
admin.site.register(CohortEnrollment)


class PSPVerificationInline(admin.TabularInline):
	model = PSPVerification
	extra = 0
	fields = ('amount_received', 'payment_reference', 'notes', 'verified_by', 'verified_at')
	readonly_fields = ('verified_by', 'verified_at')


@admin.register(PSPRegistration)
class PSPRegistrationAdmin(admin.ModelAdmin):
	list_display = (
		'full_name',
		'phone_number',
		'psp_tier',
		'cohort',
		'amount_expected',
		'status',
		'payment_till',
		'created_at',
	)
	list_filter = ('status', 'psp_tier', 'cohort')
	search_fields = ('full_name', 'phone_number', 'user__email', 'user__username')
	readonly_fields = ('id', 'created_at', 'payment_till')
	inlines = (PSPVerificationInline,)

	def payment_till(self, obj):
		return PSPRegistration.PAYMENT_TILL_NUMBER

	payment_till.short_description = 'Payment Till'

	def save_formset(self, request, form, formset, change):
		instances = formset.save(commit=False)
		for instance in instances:
			instance.verified_by = request.user
			instance.save()
			sync_psp_registration(instance.registration)
		for instance in formset.deleted_objects:
			instance.delete()
		formset.save_m2m()


@admin.register(PSPVerification)
class PSPVerificationAdmin(admin.ModelAdmin):
	list_display = (
		'registration',
		'amount_received',
		'payment_reference',
		'verified_by',
		'verified_at',
	)
	list_filter = ('verified_at',)
	search_fields = (
		'registration__full_name',
		'registration__phone_number',
		'payment_reference',
		'verified_by__email',
	)
	readonly_fields = ('id', 'verified_by', 'verified_at')

	def save_model(self, request, obj, form, change):
		obj.verified_by = request.user
		super().save_model(request, obj, form, change)
		sync_psp_registration(obj.registration)


@admin.register(CohortCoachAssignment)
class CohortCoachAssignmentAdmin(admin.ModelAdmin):
	list_display = ('cohort', 'user', 'role', 'score', 'eligibility_status', 'payout_amount', 'deployment_eligible', 'allocated_at')
	list_filter = ('role', 'cohort', 'eligibility_status', 'deployment_eligible')
	search_fields = ('cohort__title', 'user__email', 'user__username')
	readonly_fields = ('id', 'allocated_at')


@admin.register(CohortWalletEntry)
class CohortWalletEntryAdmin(admin.ModelAdmin):
	list_display = ('cohort', 'wallet', 'user', 'amount', 'description', 'created_at')
	list_filter = ('wallet', 'cohort')
	search_fields = ('cohort__title', 'user__email', 'description')
	readonly_fields = ('id', 'created_at')


@admin.register(WhatsAppInviteRequest)
class WhatsAppInviteRequestAdmin(admin.ModelAdmin):
	list_display = ('user', 'cohort', 'coach_type', 'status', 'reviewed_by', 'created_at')
	list_filter = ('status', 'coach_type', 'cohort')
	search_fields = ('user__email', 'user__username', 'cohort__title')
	readonly_fields = ('id', 'user', 'cohort', 'coach_type', 'created_at', 'reviewed_by', 'reviewed_at')
	fieldsets = (
		(None, {'fields': ('id', 'user', 'cohort', 'coach_type', 'status')}),
		('Admin review', {'fields': ('group_link', 'admin_notes', 'reviewed_by', 'reviewed_at')}),
		('Request', {'fields': ('created_at',)}),
	)


def sync_psp_registration(registration):
	verification = registration.verifications.order_by('-verified_at').first()
	if verification and abs(registration.amount_expected - verification.amount_received) < 0.01:
		registration.status = 'active' if registration.cohort_id else 'confirmed'
		registration.save(update_fields=('status',))
		if registration.cohort_id:
			CohortEnrollment.objects.get_or_create(
				user=registration.user,
				cohort=registration.cohort,
			)
	else:
		registration.status = 'failed' if verification else 'pending'
		registration.save(update_fields=('status',))


class AssessmentScheduleQuestionInline(admin.TabularInline):
	model = AssessmentScheduleQuestion
	extra = 10
	max_num = 10
	fields = ('order', 'question_type', 'prompt', 'options', 'correct_answer', 'rationale', 'requires_reasoning')
	ordering = ('order',)


@admin.register(AssessmentSchedule)
class AssessmentScheduleAdmin(admin.ModelAdmin):
	list_display = ('title', 'field', 'month', 'week', 'day', 'assessment_slot', 'difficulty', 'status', 'scheduled_for')
	list_filter = ('status', 'field', 'month', 'week', 'day', 'difficulty')
	search_fields = ('title', 'description', 'field')
	readonly_fields = ('status', 'created_by', 'reviewed_by', 'created_at', 'updated_at', 'published_at')
	date_hierarchy = 'scheduled_for'
	inlines = (AssessmentScheduleQuestionInline,)
	actions = ('submit_for_review', 'approve_content', 'schedule_content', 'publish_content', 'archive_content')
	fieldsets = (
		('Schedule', {'fields': ('month', 'week', 'day', 'assessment_slot', 'field', 'scheduled_for')}),
		('Content', {'fields': (
			'title', 'description', 'imported_external_id', 'content_source',
			'content_license', 'content_attribution', 'learning_objectives', 'difficulty',
			'duration_minutes', 'passing_score',
		)}),
		('Review and publication', {'fields': ('status', 'expert_reviewed', 'review_notes', 'created_by', 'reviewed_by', 'published_at')}),
		('Record', {'fields': ('created_at', 'updated_at')}),
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return self.has_module_permission(request)

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)

	def has_delete_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)


class SponsoredViewQuestionInline(admin.TabularInline):
	model = SponsoredViewQuestion
	extra = 10
	max_num = 10
	fields = ('order', 'prompt', 'options', 'correct_answer', 'rationale', 'requires_reasoning')
	ordering = ('order',)


@admin.register(SponsoredViewAssessment)
class SponsoredViewAssessmentAdmin(admin.ModelAdmin):
	list_display = ('title', 'field', 'week', 'slot', 'status', 'published_at')
	list_filter = ('status', 'field', 'week', 'difficulty')
	search_fields = ('title', 'description', 'field', 'imported_external_id')
	readonly_fields = (
		'status', 'created_by', 'reviewed_by', 'created_at', 'updated_at',
		'published_at', 'imported_external_id', 'content_source',
		'content_license', 'content_attribution',
	)
	inlines = (SponsoredViewQuestionInline,)
	actions = ('publish_content', 'archive_content')
	fields = (
		'week', 'slot', 'field', 'title', 'description', 'learning_objectives',
		'duration_minutes', 'difficulty', 'expert_reviewed', 'imported_external_id',
		'content_source', 'content_license', 'content_attribution', 'status',
		'created_by', 'reviewed_by', 'created_at', 'updated_at', 'published_at',
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return self.has_module_permission(request)

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)

	def has_delete_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)

	def save_model(self, request, obj, form, change):
		if change:
			obj.status = 'draft'
			obj.published_at = None
		else:
			obj.created_by = request.user
		super().save_model(request, obj, form, change)

	@admin.action(description='Publish selected validated Sponsored View assessments')
	def publish_content(self, request, queryset):
		changed = 0
		for assessment in queryset:
			if assessment.status != 'draft':
				self.message_user(request, f'{assessment.title}: only draft content can be published.', level=messages.ERROR)
				continue
			if not _sponsored_assessment_ready(assessment):
				self.message_user(request, f'{assessment.title}: requires ten complete four-option questions with explanations and three learning objectives.', level=messages.ERROR)
				continue
			assessment.status = 'published'
			assessment.reviewed_by = request.user
			assessment.published_at = timezone.now()
			assessment.save(update_fields=('status', 'reviewed_by', 'published_at', 'updated_at'))
			changed += 1
		if changed:
			self.message_user(request, f'{changed} Sponsored View assessment(s) published.')

	@admin.action(description='Archive selected Sponsored View assessments')
	def archive_content(self, request, queryset):
		changed = 0
		for assessment in queryset:
			if assessment.status != 'published':
				self.message_user(request, f'{assessment.title}: only published content can be archived.', level=messages.ERROR)
				continue
			assessment.status = 'archived'
			assessment.save(update_fields=('status', 'updated_at'))
			changed += 1
		if changed:
			self.message_user(request, f'{changed} Sponsored View assessment(s) archived.')


@admin.register(SponsoredViewPayment)
class SponsoredViewPaymentAdmin(admin.ModelAdmin):
	list_display = ('payment_reference', 'user', 'assessment', 'amount_kes', 'status', 'requested_at', 'verified_at')
	list_filter = ('status', 'requested_at')
	search_fields = ('payment_reference', 'mpesa_transaction_id', 'user__email', 'assessment__title')
	readonly_fields = tuple(field.name for field in SponsoredViewPayment._meta.fields)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False

	def save_model(self, request, obj, form, change):
		if not change and not obj.created_by_id:
			obj.created_by = request.user
		super().save_model(request, obj, form, change)

	@admin.action(description='Submit selected assessments for review')
	def submit_for_review(self, request, queryset):
		self._transition(request, queryset, 'draft', 'in_review', self._validate_review)

	@admin.action(description='Approve selected assessments')
	def approve_content(self, request, queryset):
		self._transition(request, queryset, 'in_review', 'approved', self._validate_approval, reviewed_by=request.user)

	@admin.action(description='Schedule selected approved assessments')
	def schedule_content(self, request, queryset):
		changed = 0
		for assessment in queryset:
			if assessment.status != 'approved' or assessment.scheduled_for <= timezone.now():
				self.message_user(request, f'{assessment.title}: choose approved assessments with a future schedule.', level=messages.ERROR)
				continue
			try:
				self._validate_publish(assessment)
			except ValidationError as error:
				self.message_user(request, f'{assessment.title}: {error.messages}', level=messages.ERROR)
				continue
			assessment.status = 'scheduled'
			assessment.save(update_fields=['status', 'updated_at'])
			changed += 1
		if changed:
			self.message_user(request, f'{changed} assessment(s) scheduled.')

	@admin.action(description='Publish selected approved or scheduled assessments')
	def publish_content(self, request, queryset):
		changed = 0
		for assessment in queryset:
			if assessment.status not in ('approved', 'scheduled') or assessment.scheduled_for > timezone.now():
				self.message_user(request, f'{assessment.title}: its approved schedule is not due for publication.', level=messages.ERROR)
				continue
			try:
				self._validate_publish(assessment)
			except ValidationError as error:
				self.message_user(request, f'{assessment.title}: {error.messages}', level=messages.ERROR)
				continue
			assessment.status = 'published'
			assessment.published_at = timezone.now()
			assessment.save(update_fields=['status', 'published_at', 'updated_at'])
			changed += 1
		if changed:
			self.message_user(request, f'{changed} assessment(s) published.')

	@admin.action(description='Archive selected published assessments')
	def archive_content(self, request, queryset):
		self._transition(request, queryset, 'published', 'archived')

	def _transition(self, request, queryset, expected_status, new_status, validator=None, **updates):
		changed = 0
		for assessment in queryset:
			if assessment.status != expected_status:
				self.message_user(request, f'{assessment.title}: expected {expected_status}, found {assessment.status}.', level=messages.ERROR)
				continue
			try:
				if validator:
					validator(assessment)
			except ValidationError as error:
				self.message_user(request, f'{assessment.title}: {error.messages}', level=messages.ERROR)
				continue
			for field, value in updates.items():
				setattr(assessment, field, value)
			assessment.status = new_status
			assessment.save(update_fields=['status', 'reviewed_by', 'published_at', 'updated_at'])
			changed += 1
		if changed:
			self.message_user(request, f'{changed} assessment(s) moved to {new_status}.')

	@staticmethod
	def _validate_review(assessment):
		if assessment.duration_minutes != 20:
			raise ValidationError('Main contest assessments must use a 20-minute timer.')
		if not isinstance(assessment.learning_objectives, list) or len(assessment.learning_objectives) < 3:
			raise ValidationError('At least three learning objectives are required.')
		questions = list(assessment.questions.order_by('order'))
		if [question.order for question in questions] != list(range(1, 11)):
			raise ValidationError('Exactly ten questions numbered 1 through 10 are required.')
		for question in questions:
			try:
				question.full_clean()
			except ValidationError as error:
				raise ValidationError(f'Question {question.order}: {error.messages}')
			if question.question_type != 'multiple_choice':
				raise ValidationError(f'Question {question.order} must be multiple choice.')

	@classmethod
	def _validate_approval(cls, assessment):
		cls._validate_review(assessment)
		if assessment.field in {'Medical and Health', 'Law and Society'} and not assessment.expert_reviewed:
			raise ValidationError('Mark expert review complete before approving this sensitive-field content.')

	@classmethod
	def _validate_publish(cls, assessment):
		cls._validate_approval(assessment)


@admin.register(ParticipationPayment)
class ParticipationPaymentAdmin(admin.ModelAdmin):
	list_display = ('user', 'field', 'amount_kes', 'status', 'created_at', 'verified_at')
	list_filter = ('status', 'field', 'created_at')
	search_fields = ('user__email', 'user__username', 'payment_reference', 'mpesa_transaction_id')
	readonly_fields = (
		'user', 'full_name', 'phone_number', 'field', 'amount_kes', 'till_number',
		'payment_reference', 'mpesa_transaction_id', 'status', 'verification_notes',
		'rejection_reason', 'created_at', 'verified_at', 'verified_by', 'expires_at',
	)
	fieldsets = (
		(None, {'fields': ('user', 'full_name', 'phone_number', 'field', 'amount_kes', 'till_number')}),
		('Payment Reference', {'fields': ('payment_reference', 'mpesa_transaction_id')}),
		('Verification', {'fields': ('status', 'verified_by', 'verified_at', 'verification_notes', 'rejection_reason', 'expires_at')}),
		('Record', {'fields': ('created_at',)}),
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(ParticipationPaymentEvent)
class ParticipationPaymentEventAdmin(admin.ModelAdmin):
	list_display = ('payment', 'decision', 'actor', 'created_at')
	list_filter = ('decision', 'created_at')
	search_fields = ('payment__payment_reference', 'payment__user__email', 'actor__email')
	readonly_fields = ('payment', 'actor', 'decision', 'notes', 'confirmed_transaction_id', 'created_at')

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(AssessmentScheduleAttempt)
class AssessmentScheduleAttemptAdmin(admin.ModelAdmin):
	list_display = ('user', 'assessment', 'status', 'score', 'started_at', 'submitted_at')
	list_filter = ('status', 'assessment__field', 'started_at', 'is_flagged')
	search_fields = ('user__email', 'user__username', 'assessment__title')
	readonly_fields = (
		'user', 'assessment', 'answers', 'question_order', 'started_at',
		'submitted_at', 'duration_seconds',
		'tab_switches', 'time_anomalies', 'ip_address', 'user_agent',
	)
	fieldsets = (
		(None, {'fields': ('user', 'assessment', 'status', 'score')}),
		('Response data', {'fields': ('answers', 'question_order')}),
		('Timing', {'fields': ('started_at', 'submitted_at', 'duration_seconds')}),
		('Anti-cheat', {'fields': ('tab_switches', 'time_anomalies', 'ip_address', 'user_agent', 'is_flagged', 'flag_reason')}),
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_delete_permission(self, request, obj=None):
		return False

	def save_model(self, request, obj, form, change):
		previous = None
		if change:
			previous = AssessmentScheduleAttempt.objects.get(pk=obj.pk)
		super().save_model(request, obj, form, change)
		if previous and (
			previous.status != obj.status
			or previous.score != obj.score
			or previous.is_flagged != obj.is_flagged
		):
			from .support_views import sync_support_eligibilities_for_user
			transaction.on_commit(
				lambda user=obj.user: sync_support_eligibilities_for_user(user)
			)


@admin.register(SupportProgram)
class SupportProgramAdmin(admin.ModelAdmin):
	list_display = ('title', 'program_type', 'merit_cutoff', 'funding_status', 'status', 'deadline')
	list_filter = ('program_type', 'funding_status', 'status')
	search_fields = ('title', 'description', 'eligibility_rules')
	readonly_fields = ('created_by', 'created_at', 'updated_at')
	fieldsets = (
		('Programme', {'fields': ('title', 'description', 'program_type', 'status', 'deadline')}),
		('Published eligibility and funding', {'fields': (
			'eligibility_rules', 'merit_cutoff', 'eligibility_config', 'funding_status',
		)}),
		('Application form', {'fields': ('application_fields',)}),
		('Record', {'fields': ('created_by', 'created_at', 'updated_at')}),
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return self.has_module_permission(request)

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_delete_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.applications.exists()
		)

	def save_model(self, request, obj, form, change):
		if not change:
			obj.created_by = request.user
		super().save_model(request, obj, form, change)
		if obj.status in ('published', 'closed'):
			transaction.on_commit(lambda program_id=obj.pk: reconcile_support_program(program_id))


class SupportApplicationAdminForm(forms.ModelForm):
	class Meta:
		model = SupportApplication
		fields = '__all__'

	def clean(self):
		cleaned_data = super().clean()
		if not self.instance.pk:
			return cleaned_data

		previous = SupportApplication.objects.get(pk=self.instance.pk)
		next_status = cleaned_data.get('status', previous.status)
		allowed = {
			'submitted': {'submitted', 'under_review', 'awaiting_information', 'declined'},
			'under_review': {'under_review', 'approved', 'awaiting_funding', 'awaiting_information', 'declined'},
			'approved': {'approved', 'awaiting_funding', 'payment_processing', 'declined'},
			'awaiting_funding': {'awaiting_funding', 'payment_processing', 'declined'},
			'payment_processing': {'payment_processing', 'paid', 'declined'},
			'awaiting_information': {'awaiting_information', 'under_review', 'declined'},
			'paid': {'paid'},
			'declined': {'declined'},
		}
		if next_status not in allowed[previous.status]:
			self.add_error('status', 'This application status transition is not allowed.')
		if next_status == 'declined' and not (cleaned_data.get('admin_reason') or '').strip():
			self.add_error('admin_reason', 'Provide the reason for declining this application.')
		if next_status == 'paid' and not (cleaned_data.get('payment_reference') or '').strip():
			self.add_error('payment_reference', 'Record the payment reference before confirming payment.')
		if next_status in ('payment_processing', 'paid') and self.instance.program.funding_status != 'funded':
			self.add_error('status', 'Mark the programme as funded before processing payment.')
		return cleaned_data


@admin.register(SupportApplication)
class SupportApplicationAdmin(admin.ModelAdmin):
	form = SupportApplicationAdminForm
	list_display = (
		'program_title_at_application', 'full_name', 'registered_phone_number',
		'mpesa_number', 'merit_score_at_application',
		'tutorial_consistency_weeks_at_application', 'status', 'submitted_at',
	)
	list_filter = ('status', 'program_type_at_application', 'submitted_at')
	search_fields = (
		'program_title_at_application', 'full_name', 'registered_phone_number',
		'mpesa_number', 'user__email', 'payment_reference',
	)
	readonly_fields = (
		'user', 'program', 'eligibility', 'program_title_at_application',
		'program_type_at_application', 'eligibility_rules_at_application',
		'merit_cutoff_at_application', 'full_name', 'registered_phone_number',
		'mpesa_number', 'merit_score_at_application',
		'tutorial_consistency_weeks_at_application', 'reviewed_by',
		'application_fields_at_application', 'application_data',
		'payment_confirmed_by', 'payment_confirmed_at', 'submitted_at', 'updated_at',
	)
	fieldsets = (
		('Applicant and programme', {'fields': (
			'user', 'program', 'program_title_at_application',
			'program_type_at_application', 'full_name',
			'registered_phone_number', 'mpesa_number',
			'application_fields_at_application', 'application_data',
		)}),
		('Eligibility snapshot', {'fields': (
			'eligibility', 'merit_cutoff_at_application',
			'merit_score_at_application', 'tutorial_consistency_weeks_at_application',
			'eligibility_rules_at_application',
		)}),
		('Review decision', {'fields': ('status', 'admin_reason', 'reviewed_by')}),
		('Payment confirmation', {'fields': (
			'payment_reference', 'payment_confirmed_at', 'payment_confirmed_by',
		)}),
		('Record', {'fields': ('submitted_at', 'updated_at')}),
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.status in ('paid', 'declined')
		)

	def has_delete_permission(self, request, obj=None):
		return False

	def save_model(self, request, obj, form, change):
		changed = False
		if change:
			previous = SupportApplication.objects.get(pk=obj.pk)
			changed = (
				obj.status != previous.status
				or obj.admin_reason != previous.admin_reason
				or obj.payment_reference != previous.payment_reference
			)
			if obj.status != previous.status:
				obj.reviewed_by = request.user
			if obj.status == 'paid' and previous.status != 'paid':
				obj.payment_confirmed_by = request.user
				obj.payment_confirmed_at = timezone.now()
		super().save_model(request, obj, form, change)
		if changed:
			SupportApplicationEvent.objects.create(
				application=obj,
				actor=request.user,
				status=obj.status,
				reason=obj.admin_reason,
				payment_reference=obj.payment_reference,
			)
			if obj.status != previous.status:
				from apps.notifications.utils import send_notification
				send_notification(
					user=obj.user,
					notification_type='opportunity',
					title='Opportunity application updated',
					message=(
						f'{obj.program_title_at_application}: your application is now '
						f'{obj.status.replace("_", " ")}.'
						+ (f' {obj.admin_reason}' if obj.admin_reason else '')
					),
					action_url='/opportunities',
					metadata={
						'application_id': str(obj.id),
						'program_id': str(obj.program_id),
						'status': obj.status,
					},
				)


@admin.register(SupportEligibility)
class SupportEligibilityAdmin(admin.ModelAdmin):
	list_display = (
		'user', 'program', 'merit_score', 'merit_cutoff_at_eligibility',
		'tutorial_consistency_weeks', 'eligible', 'notified_at',
	)
	list_filter = ('eligible', 'program')
	search_fields = ('user__email', 'user__username', 'program__title')
	readonly_fields = (
		'user', 'program', 'merit_score', 'merit_cutoff_at_eligibility',
		'completed_contests', 'tutorial_consistency_weeks', 'eligible',
		'notified_at', 'created_at', 'updated_at',
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(SupportApplicationEvent)
class SupportApplicationEventAdmin(admin.ModelAdmin):
	list_display = ('application', 'status', 'actor', 'created_at')
	list_filter = ('status', 'created_at')
	search_fields = ('application__full_name', 'application__program_title_at_application', 'actor__email')
	readonly_fields = ('application', 'actor', 'status', 'reason', 'payment_reference', 'created_at')

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False
