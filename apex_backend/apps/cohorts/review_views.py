from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin
from .content_validation import PLACEHOLDER_TERMS, question_set_is_complete
from .models import AssessmentSchedule, SponsoredViewAssessment, Tutorial
from .tutorial_schedule import CAPABILITY_FIELDS


LIBRARIES = {
    'tutorials': Tutorial,
    'main-contest': AssessmentSchedule,
    'sponsored-view': SponsoredViewAssessment,
}
SENSITIVE_FIELDS = {'Medical and Health', 'Law and Society'}
TUTORIAL_SECTIONS = (
    'concept_explanation',
    'terminology_and_components',
    'why_it_matters',
    'how_it_works',
    'worked_examples',
    'common_mistakes',
    'practical_application',
    'decisions_and_tradeoffs',
    'related_concepts',
)


class ContentReviewActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=('submit_for_review', 'approve', 'publish', 'archive'),
    )


def _quality_errors(content, library):
    errors = []
    if content.field not in CAPABILITY_FIELDS:
        errors.append('Choose an official study area.')
    if (
        not content.title.strip()
        or not content.description.strip()
        or PLACEHOLDER_TERMS.search(content.title)
        or PLACEHOLDER_TERMS.search(content.description)
    ):
        errors.append('A title and description are required.')
    objectives = content.learning_objectives
    if (
        not isinstance(objectives, list)
        or len(objectives) < 3
        or any(
            not isinstance(item, str)
            or not item.strip()
            or PLACEHOLDER_TERMS.search(item)
            for item in objectives
        )
    ):
        errors.append('At least three non-empty learning objectives are required.')
    if not question_set_is_complete(list(content.questions.order_by('order'))):
        errors.append('Exactly ten unique multiple-choice questions with four options, a valid answer, and an explanation are required.')
    if library == 'tutorials':
        if any(not getattr(content, section).strip() for section in TUTORIAL_SECTIONS):
            errors.append('Complete all nine structured teaching sections.')
    elif library == 'main-contest' and content.duration_minutes != 20:
        errors.append('Main Contest assessments must use a 20-minute timer.')
    elif library == 'sponsored-view' and content.duration_minutes <= 0:
        errors.append('Set a positive assessment duration.')
    return errors


def _content_data(content, library):
    questions = content.questions.order_by('order')
    data = {
        'id': str(content.id),
        'library': library,
        'title': content.title,
        'description': content.description,
        'field': content.field,
        'status': content.status,
        'learning_objectives': content.learning_objectives,
        'expert_reviewed': content.expert_reviewed,
        'created_at': content.created_at,
        'updated_at': content.updated_at,
        'published_at': content.published_at,
        'questions': [{
            'id': str(question.id),
            'order': question.order,
            'prompt': question.prompt,
            'options': question.options,
            'correct_answer': question.correct_answer,
            'rationale': question.rationale,
            'requires_reasoning': question.requires_reasoning,
        } for question in questions],
        'quality_errors': _quality_errors(content, library),
    }
    if library == 'tutorials':
        data.update({
            'month': content.month,
            'week': content.week,
            'day': content.get_day_display(),
            'slot': content.daily_slot,
            'scheduled_for': content.scheduled_for,
            'teaching_sections': {
                section: getattr(content, section)
                for section in TUTORIAL_SECTIONS
            },
        })
    elif library == 'main-contest':
        data.update({
            'month': content.month,
            'week': content.week,
            'day': content.get_day_display(),
            'slot': content.assessment_slot,
            'scheduled_for': content.scheduled_for,
            'duration_minutes': content.duration_minutes,
            'passing_score': content.passing_score,
        })
    else:
        data.update({
            'week': content.week,
            'slot': content.slot,
            'duration_minutes': content.duration_minutes,
        })
    return data


class AdminAssessmentReviewListView(APIView):
    permission_classes = (IsAuthenticated, IsAdmin)

    def get(self, request):
        library = request.query_params.get('library', 'tutorials')
        model = LIBRARIES.get(library)
        if model is None:
            raise serializers.ValidationError({'library': 'Choose tutorials, main-contest, or sponsored-view.'})

        queryset = model.objects.prefetch_related('questions').order_by('field', 'title')
        content_status = request.query_params.get('status')
        if content_status:
            if content_status not in {value for value, _label in model._meta.get_field('status').choices}:
                raise serializers.ValidationError({'status': 'Choose a valid content status.'})
            queryset = queryset.filter(status=content_status)
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(field__icontains=search))

        try:
            page_number = int(request.query_params.get('page', '1'))
        except (TypeError, ValueError) as error:
            raise serializers.ValidationError({'page': 'Page must be a positive integer.'}) from error
        if page_number < 1:
            raise serializers.ValidationError({'page': 'Page must be a positive integer.'})

        paginator = Paginator(queryset, 20)
        try:
            page = paginator.page(page_number)
        except EmptyPage:
            page = paginator.page(paginator.num_pages) if paginator.num_pages else paginator.page(1)
        return Response({
            'count': paginator.count,
            'page': page.number,
            'page_size': 20,
            'results': [_content_data(item, library) for item in page.object_list],
        })


class AdminAssessmentReviewActionView(APIView):
    permission_classes = (IsAuthenticated, IsAdmin)

    def post(self, request, library, content_id):
        model = LIBRARIES.get(library)
        if model is None:
            raise serializers.ValidationError({'library': 'Choose tutorials, main-contest, or sponsored-view.'})
        serializer = ContentReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']

        with transaction.atomic():
            content = model.objects.select_for_update().prefetch_related('questions').filter(pk=content_id).first()
            if content is None:
                return Response({'detail': 'Assessment not found.'}, status=status.HTTP_404_NOT_FOUND)
            error = self._transition(content, library, action, request.user)
            if error:
                return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
            content.save(update_fields=('status', 'reviewed_by', 'published_at', 'updated_at'))
        return Response(_content_data(content, library))

    @staticmethod
    def _transition(content, library, action, reviewer):
        if action == 'submit_for_review':
            if library == 'sponsored-view' or content.status != 'draft':
                return 'Only draft Tutorials and Main Contest assessments can be submitted for review.'
            errors = _quality_errors(content, library)
            if errors:
                return 'Content is not ready for review: ' + ' '.join(errors)
            content.status = 'in_review'
            return ''

        if action == 'approve':
            if library == 'sponsored-view' or content.status != 'in_review':
                return 'Only assessments in review can be approved.'
            errors = _quality_errors(content, library)
            if errors:
                return 'Content is not ready for approval: ' + ' '.join(errors)
            if content.field in SENSITIVE_FIELDS and not content.expert_reviewed:
                return 'Qualified expert review is required before approving this study area.'
            content.status = 'approved'
            content.reviewed_by = reviewer
            return ''

        if action == 'publish':
            allowed = content.status == 'draft' if library == 'sponsored-view' else content.status in {'approved', 'scheduled'}
            if not allowed:
                return 'Only draft Sponsored View or approved/scheduled assessments can be published.'
            errors = _quality_errors(content, library)
            if errors:
                return 'Content is not ready to publish: ' + ' '.join(errors)
            if content.field in SENSITIVE_FIELDS and not content.expert_reviewed:
                return 'Qualified expert review is required before publishing this study area.'
            scheduled_for = getattr(content, 'scheduled_for', None)
            if scheduled_for and scheduled_for > timezone.now():
                return 'The scheduled publication time has not arrived.'
            content.status = 'published'
            content.reviewed_by = reviewer
            content.published_at = timezone.now()
            return ''

        if action == 'archive':
            if content.status != 'published':
                return 'Only published assessments can be archived.'
            content.status = 'archived'
            return ''

        return 'Unsupported review action.'
