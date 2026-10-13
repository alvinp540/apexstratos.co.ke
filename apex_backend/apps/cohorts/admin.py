from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
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
)
from .allocation import allocate_cohort_rewards
from .forms import DailyTutorialBundleForm
from .tutorial_import import import_daily_tutorial_bundle


class TutorialQuestionInline(admin.TabularInline):
	model = TutorialQuestion
	extra = 5
	max_num = 5
	fields = ('order', 'question_type', 'prompt', 'options', 'correct_answer', 'rationale')
	ordering = ('order',)


@admin.register(Tutorial)
class TutorialAdmin(admin.ModelAdmin):
	change_list_template = 'admin/cohorts/tutorial/change_list.html'
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
			'title', 'description', 'learning_objectives', 'concept_explanation',
			'terminology_and_components', 'why_it_matters', 'how_it_works',
			'worked_examples', 'common_mistakes', 'practical_application',
			'decisions_and_tradeoffs', 'related_concepts', 'difficulty',
			'duration_minutes', 'video', 'related_assessment_ids',
		)}),
		('Review and publication', {'fields': ('status', 'expert_reviewed', 'review_notes', 'created_by', 'reviewed_by', 'published_at')}),
		('Record', {'fields': ('created_at', 'updated_at')}),
	)

	def get_urls(self):
		custom_urls = [
			path('daily-upload/', self.admin_site.admin_view(self.daily_upload_view), name='cohorts_tutorial_daily_upload'),
		]
		return custom_urls + super().get_urls()

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return self.has_module_permission(request)

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_delete_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def daily_upload_view(self, request):
		if not request.user.is_admin:
			return HttpResponseForbidden()
		form = DailyTutorialBundleForm(request.POST or None, request.FILES or None)
		if request.method == 'POST' and form.is_valid():
			try:
				tutorials = import_daily_tutorial_bundle(
					uploaded_bundle=form.cleaned_data['bundle'],
					month=form.cleaned_data['month'],
					week=form.cleaned_data['week'],
					day=int(form.cleaned_data['day']),
					scheduled_for=form.cleaned_data['scheduled_for'],
					created_by=request.user,
				)
			except ValidationError as error:
				form.add_error('bundle', error)
			else:
				self.message_user(
					request,
					f'Imported {len(tutorials)} tutorials as Drafts. Review them before publishing.',
					level=messages.SUCCESS,
				)
				return HttpResponseRedirect(reverse('admin:cohorts_tutorial_changelist'))

		context = {
			**self.admin_site.each_context(request),
			'title': 'Upload tutorials for one day',
			'opts': self.model._meta,
			'form': form,
			'upload_url': reverse('admin:cohorts_tutorial_daily_upload'),
		}
		return TemplateResponse(request, 'admin/cohorts/tutorial/daily_upload.html', context)

	def save_model(self, request, obj, form, change):
		if change:
			obj.status = Tutorial.STATUS_CHOICES[0][0]
			obj.published_at = None
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
		if not tutorial.video:
			raise ValidationError('Upload an internal video before requesting review.')
		teaching_sections = (
			'concept_explanation', 'terminology_and_components', 'why_it_matters',
			'how_it_works', 'worked_examples', 'common_mistakes',
			'practical_application', 'decisions_and_tradeoffs', 'related_concepts',
		)
		if any(not getattr(tutorial, section).strip() for section in teaching_sections):
			raise ValidationError('Complete all structured teaching sections before requesting review.')
		if not isinstance(tutorial.learning_objectives, list) or len(tutorial.learning_objectives) < 3:
			raise ValidationError('At least three learning objectives are required.')
		question_orders = list(tutorial.questions.order_by('order').values_list('order', flat=True))
		if question_orders != [1, 2, 3, 4, 5]:
			raise ValidationError('Exactly five tutorial questions numbered 1 through 5 are required.')

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
	extra = 5
	max_num = 5
	fields = ('order', 'question_type', 'prompt', 'options', 'correct_answer', 'rationale')
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
			'title', 'description', 'learning_objectives', 'difficulty',
			'duration_minutes', 'video', 'passing_score',
		)}),
		('Review and publication', {'fields': ('status', 'expert_reviewed', 'review_notes', 'created_by', 'reviewed_by', 'published_at')}),
		('Record', {'fields': ('created_at', 'updated_at')}),
	)

	def has_module_permission(self, request):
		return bool(request.user.is_authenticated and request.user.is_admin)

	def has_view_permission(self, request, obj=None):
		return self.has_module_permission(request)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)

	def has_delete_permission(self, request, obj=None):
		return self.has_module_permission(request) and not (
			obj is not None and obj.attempts.exists()
		)

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
		if not assessment.video or not assessment.video.storage.exists(assessment.video.name):
			raise ValidationError('Upload an available internal assessment video before review.')
		if assessment.duration_minutes != 20:
			raise ValidationError('Main contest assessments must use a 20-minute timer.')
		if not isinstance(assessment.learning_objectives, list) or len(assessment.learning_objectives) < 3:
			raise ValidationError('At least three learning objectives are required.')
		questions = list(assessment.questions.order_by('order'))
		if [question.order for question in questions] != [1, 2, 3, 4, 5]:
			raise ValidationError('Exactly five questions numbered 1 through 5 are required.')
		for question in questions:
			try:
				question.full_clean()
			except ValidationError as error:
				raise ValidationError(f'Question {question.order}: {error.messages}')

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
		'user', 'assessment', 'answers', 'question_order', 'video_watched_seconds',
		'video_completed', 'started_at', 'submitted_at', 'duration_seconds',
		'tab_switches', 'time_anomalies', 'ip_address', 'user_agent',
	)
	fieldsets = (
		(None, {'fields': ('user', 'assessment', 'status', 'score')}),
		('Response data', {'fields': ('answers', 'question_order', 'video_watched_seconds', 'video_completed')}),
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
