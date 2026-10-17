from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from datetime import timedelta
import random

from .models import (
    Cohort,
    Assessment,
    AssessmentAttempt,
    CohortEnrollment,
    Tutorial,
    TutorialAttempt,
    TutorialProgress,
)
from .serializers import (
    CohortSerializer, AssessmentSerializer, AssessmentAttemptSerializer, HeartbeatSerializer,
    PSPRegistrationCreateSerializer,
    TutorialQuerySerializer, TutorialSerializer,
)
from .models import PSPRegistration, PSPVerification, WhatsAppInviteRequest, CohortCoachAssignment
from .serializers import PSPRegistrationSerializer, PSPVerificationSerializer, WhatsAppInviteRequestSerializer, CoachPayoutSerializer
from .anti_cheat import flag_attempt
from apps.trust_engine.engine import recalculate_trust_score
from apps.accounts.permissions import IsAdmin
from .allocation import allocate_cohort_rewards
from .weekly_schedule import activity_window, attempt_deadline, weekly_schedule
from utils.pagination import StandardResultsPagination


class TutorialListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        filters = TutorialQuerySerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        query = dict(filters.validated_data)
        library_week = query.pop('week', None)
        topic = query.pop('topic', '').strip()
        tutorials = Tutorial.objects.filter(
            status__in=('published', 'scheduled'),
        ).annotate(question_count=Count('questions')).filter(
            question_count=10,
        ).prefetch_related(
            'questions',
            Prefetch(
                'progress',
                queryset=TutorialProgress.objects.filter(user=request.user),
                to_attr='current_user_progress',
            ),
        ).order_by('month', 'week', 'day', 'field', 'daily_slot')
        if library_week is not None:
            query['month'] = (library_week - 1) // 4 + 1
            query['week'] = (library_week - 1) % 4 + 1
        tutorials = tutorials.filter(**query)
        if topic:
            tutorials = tutorials.filter(Q(title__icontains=topic) | Q(description__icontains=topic))
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(tutorials, request)
        return paginator.get_paginated_response(TutorialSerializer(
            page,
            many=True,
            context={'request': request, 'include_attempt': False},
        ).data)


class TutorialDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, tutorial_id):
        tutorial = get_object_or_404(
            Tutorial.objects.prefetch_related(
                'questions',
                Prefetch(
                    'progress',
                    queryset=TutorialProgress.objects.filter(user=request.user),
                    to_attr='current_user_progress',
                ),
                Prefetch(
                    'attempts',
                    queryset=TutorialAttempt.objects.filter(user=request.user).order_by('-started_at'),
                    to_attr='current_user_attempts',
                ),
            ),
            id=tutorial_id,
            status__in=('published', 'scheduled'),
        )
        return Response(TutorialSerializer(tutorial).data)


def _tutorial_is_ready(tutorial):
    questions = list(tutorial.questions.order_by('order'))
    if [question.order for question in questions] != list(range(1, 11)):
        return False
    return all(
        question.question_type == 'multiple_choice'
        and isinstance(question.options, list)
        and len(question.options) >= 2
        and question.correct_answer in question.options
        for question in questions
    )


def _tutorial_attempt_response(attempt, *, reveal_answers=False):
    questions = attempt.question_snapshot
    public_questions = []
    answers = {}
    reasoning = {}
    for question_id, value in attempt.answers.items():
        answers[question_id] = value.get('answer', '') if isinstance(value, dict) else value
        if isinstance(value, dict) and value.get('reasoning'):
            reasoning[question_id] = value['reasoning']
    for question in questions:
        item = {
            'id': question['id'],
            'order': question['order'],
            'prompt': question['prompt'],
            'options': question['options'],
            'requires_reasoning': question.get('requires_reasoning', False),
        }
        if reveal_answers and attempt.status == 'graded':
            item['correct_answer'] = question['correct_answer']
            item['rationale'] = question['rationale']
            item['selected_answer'] = answers.get(question['id'])
            item['written_reasoning'] = reasoning.get(question['id'], '')
        public_questions.append(item)
    now = timezone.now()
    try:
        duration_seconds = (attempt.tutorial.duration_minutes or 20) * 60
        deadline = attempt_deadline('tutorials', attempt.started_at, duration_seconds)
    except ValueError:
        deadline = None
    return {
        'id': str(attempt.id),
        'tutorial': str(attempt.tutorial_id),
        'title': attempt.tutorial.title,
        'questions': public_questions,
        'answers': answers,
        'reasoning': reasoning,
        'score': attempt.score,
        'status': attempt.status,
        'started_at': attempt.started_at,
        'deadline_at': deadline,
        'server_time': now,
        'time_remaining': max(0, int((deadline - now).total_seconds())) if deadline else 0,
        'submitted_at': attempt.submitted_at,
    }


class StartTutorialAttemptView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, tutorial_id):
        with transaction.atomic():
            tutorial = get_object_or_404(
                Tutorial.objects.select_for_update().prefetch_related('questions'),
                id=tutorial_id,
                status__in=('published', 'scheduled'),
            )
            now = timezone.now()
            window = activity_window('tutorials', now)
            if window is None:
                return Response(
                    {'error': 'Tutorial assessments are available Monday through Thursday in EAT.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            attempt = TutorialAttempt.objects.filter(
                user=request.user,
                tutorial=tutorial,
            ).order_by('-started_at').first()
            if attempt is not None:
                if attempt.status == 'graded':
                    return Response(
                        _tutorial_attempt_response(attempt, reveal_answers=True),
                        status=status.HTTP_200_OK,
                    )
                if attempt.status != 'in_progress':
                    return Response(
                        {'error': 'This tutorial attempt is no longer active.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                deadline = attempt_deadline(
                    'tutorials',
                    attempt.started_at,
                    (tutorial.duration_minutes or 20) * 60,
                )
                if now >= deadline:
                    attempt.status = 'timed_out'
                    attempt.submitted_at = now
                    attempt.save(update_fields=('status', 'submitted_at'))
                    return Response(
                        {'error': 'The tutorial deadline has expired.'},
                        status=status.HTTP_410_GONE,
                    )
                return Response(_tutorial_attempt_response(attempt), status=status.HTTP_200_OK)

            if not _tutorial_is_ready(tutorial):
                return Response(
                    {'error': 'This tutorial requires ten valid multiple-choice questions.'},
                    status=status.HTTP_409_CONFLICT,
                )

            questions = list(tutorial.questions.order_by('order'))
            snapshot = [
                {
                    'id': str(question.id),
                    'order': question.order,
                    'prompt': question.prompt,
                    'options': question.options,
                    'correct_answer': question.correct_answer,
                    'rationale': question.rationale,
                    'requires_reasoning': question.requires_reasoning,
                }
                for question in questions
            ]
            try:
                with transaction.atomic():
                    attempt = TutorialAttempt.objects.create(
                        user=request.user,
                        tutorial=tutorial,
                        question_snapshot=snapshot,
                        started_at=now,
                    )
            except IntegrityError:
                attempt = TutorialAttempt.objects.get(
                    user=request.user,
                    tutorial=tutorial,
                    status='in_progress',
                )
                return Response(_tutorial_attempt_response(attempt), status=status.HTTP_200_OK)
        return Response(
            _tutorial_attempt_response(attempt),
            status=status.HTTP_201_CREATED,
        )


class SaveTutorialAttemptView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, attempt_id):
        with transaction.atomic():
            attempt = get_object_or_404(
                TutorialAttempt.objects.select_for_update().select_related('tutorial'),
                id=attempt_id,
                user=request.user,
            )
            if attempt.status != 'in_progress':
                return Response(
                    {'error': 'This tutorial attempt is no longer active.'},
                    status=status.HTTP_409_CONFLICT,
                )
            now = timezone.now()
            if now >= attempt_deadline(
                'tutorials',
                attempt.started_at,
                (attempt.tutorial.duration_minutes or 20) * 60,
            ):
                attempt.status = 'timed_out'
                attempt.submitted_at = now
                attempt.save(update_fields=('status', 'submitted_at'))
                return Response(
                    {'error': 'The tutorial deadline has expired.'},
                    status=status.HTTP_410_GONE,
                )

            answers = request.data.get('answers', {})
            reasoning = request.data.get('reasoning', {})
            if not isinstance(answers, dict) or not isinstance(reasoning, dict):
                return Response(
                    {'error': 'Answers and reasoning must be question-to-value maps.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            questions = {item['id']: item for item in attempt.question_snapshot}
            normalized = dict(attempt.answers)
            for raw_id, answer in answers.items():
                question_id = str(raw_id)
                if question_id not in questions or answer not in questions[question_id]['options']:
                    return Response(
                        {'error': 'One or more answers are invalid for this tutorial version.'},
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
        return Response(_tutorial_attempt_response(attempt))


class SubmitTutorialAttemptView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, attempt_id):
        with transaction.atomic():
            attempt = get_object_or_404(
                TutorialAttempt.objects.select_for_update().select_related('tutorial'),
                id=attempt_id,
                user=request.user,
            )
            if attempt.status == 'graded':
                from .support_views import sync_support_eligibilities_for_user
                sync_support_eligibilities_for_user(attempt.user)
                return Response(_tutorial_attempt_response(attempt, reveal_answers=True))
            if attempt.status != 'in_progress':
                return Response(
                    {'error': 'This tutorial attempt is no longer active.'},
                    status=status.HTTP_409_CONFLICT,
                )
            now = timezone.now()
            deadline = attempt_deadline(
                'tutorials',
                attempt.started_at,
                (attempt.tutorial.duration_minutes or 20) * 60,
            )
            if now >= deadline:
                attempt.status = 'timed_out'
                attempt.submitted_at = now
                attempt.save(update_fields=('status', 'submitted_at'))
                return Response(
                    {'error': 'The tutorial deadline has expired.'},
                    status=status.HTTP_410_GONE,
                )
            answers = request.data.get('answers')
            question_map = {item['id']: item for item in attempt.question_snapshot}
            if not isinstance(answers, dict) or set(map(str, answers)) != set(question_map):
                return Response(
                    {'error': 'Submit one answer for each of the ten questions.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            normalized = {str(key): value for key, value in answers.items()}
            if any(
                answer not in question_map[question_id]['options']
                for question_id, answer in normalized.items()
            ):
                return Response(
                    {'error': 'One or more answers are invalid for this tutorial version.'},
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
                if question_id not in question_map or not isinstance(text, str) or len(text) > 5000:
                    return Response(
                        {'error': 'One or more written reasoning responses are invalid.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if text.strip():
                    normalized_reasoning[question_id] = text.strip()
            if any(
                question.get('requires_reasoning')
                and not normalized_reasoning.get(question['id'])
                for question in attempt.question_snapshot
            ):
                return Response(
                    {'error': 'Written reasoning is required for one or more questions.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            score = round(
                100 * sum(
                    normalized[question['id']] == question['correct_answer']
                    for question in attempt.question_snapshot
                ) / 10,
                2,
            )
            attempt.answers = {
                question_id: {
                    'answer': answer,
                    'reasoning': normalized_reasoning.get(question_id, ''),
                }
                for question_id, answer in normalized.items()
            }
            attempt.score = score
            attempt.status = 'graded'
            attempt.submitted_at = now
            attempt.save(update_fields=('answers', 'score', 'status', 'submitted_at'))

            progress, _ = TutorialProgress.objects.select_for_update().get_or_create(
                user=request.user,
                tutorial=attempt.tutorial,
            )
            progress.attempt_count += 1
            progress.best_score = max(progress.best_score, score)
            progress.completed_at = progress.completed_at or now
            progress.last_attempt = attempt
            progress.save(update_fields=(
                'attempt_count', 'best_score', 'completed_at', 'last_attempt', 'updated_at',
            ))
            from .support_views import sync_support_eligibilities_for_user
            sync_support_eligibilities_for_user(attempt.user)
        return Response(_tutorial_attempt_response(attempt, reveal_answers=True))


class WeeklyScheduleView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(weekly_schedule())


class CohortListView(APIView):
    def get(self, request):
        if not request.user.is_admin:
            return DailyAvailableCohortsView().get(request)
        cohorts = Cohort.objects.filter(status='open')
        return Response(CohortSerializer(cohorts, many=True).data)


class DailyAvailableCohortsView(APIView):
    """
    Returns up to 6 cohort assessments available for the requesting user for the day.

    Behavior:
    - Prioritize cohorts matching the user's profile.profession, then fall back to open cohorts.
    - Exclude cohorts the user has already attempted or enrolled in (no repeats).
    - Enforce a per-day limit of 6 cohorts per user.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        profession = getattr(profile, 'profession', None) if profile else None

        # how many cohorts user already ran today
        today = timezone.now().date()
        attempts_today = AssessmentAttempt.objects.filter(
            user=user,
            submitted_at__date=today,
        ).count()
        remaining = max(0, 6 - attempts_today)
        if remaining == 0:
            return Response([])

        # build candidate cohorts
        attempted_assessment_ids = AssessmentAttempt.objects.filter(user=user).values_list('assessment_id', flat=True)
        enrolled_cohort_ids = CohortEnrollment.objects.filter(user=user).values_list('cohort_id', flat=True)

        qs = Cohort.objects.filter(status='open')
        if profession:
            prof_qs = qs.filter(profession=profession)
        else:
            prof_qs = Cohort.objects.none()

        fallback_qs = qs.exclude(id__in=prof_qs.values_list('id', flat=True))

        # combine prioritized list
        candidates = list(prof_qs.order_by('start_date')) + list(fallback_qs.order_by('start_date'))

        selected = []
        for cohort in candidates:
            if len(selected) >= remaining:
                break
            if cohort.id in enrolled_cohort_ids:
                continue
            # skip if any assessment in cohort already attempted by user
            cohort_assessments = list(cohort.assessments.filter(is_active=True))
            already = False
            for a in cohort_assessments:
                if a.id in attempted_assessment_ids:
                    already = True
                    break
            if already:
                continue
            selected.append(cohort)

        return Response(CohortSerializer(selected, many=True).data)


class CohortDetailView(APIView):
    def get(self, request, cohort_id):
        cohort = get_object_or_404(Cohort, id=cohort_id)
        return Response(CohortSerializer(cohort).data)


class CohortEnrollView(APIView):
    def post(self, request, cohort_id):
        cohort = get_object_or_404(Cohort, id=cohort_id, status='open')
        if not PSPRegistration.objects.filter(
            user=request.user, cohort=cohort, status='active'
        ).exists():
            return Response(
                {'error': 'Complete and verify your PSP payment before joining this cohort.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if cohort.enrollments.count() >= cohort.max_participants:
            return Response({'error': 'Cohort is full.'}, status=status.HTTP_400_BAD_REQUEST)
        _, created = CohortEnrollment.objects.get_or_create(user=request.user, cohort=cohort)
        if not created:
            return Response({'error': 'Already enrolled.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Enrolled successfully.'}, status=status.HTTP_201_CREATED)


class CohortAssessmentsView(APIView):
    def get(self, request, cohort_id):
        assessments = Assessment.objects.filter(
            cohort_id=cohort_id,
            is_active=True,
        ).annotate(
            question_count=Count('questions'),
            mcq_count=Count('questions', filter=Q(questions__question_type='mcq')),
        ).filter(question_count=10, mcq_count=10)
        return Response(AssessmentSerializer(assessments, many=True).data)


class StartAssessmentView(APIView):
    def post(self, request, assessment_id):
        assessment = get_object_or_404(Assessment, id=assessment_id, is_active=True)
        if assessment.questions.count() != 10 or assessment.questions.exclude(question_type='mcq').exists():
            return Response(
                {'error': 'This assessment is unavailable until it has exactly ten multiple-choice questions.'},
                status=status.HTTP_409_CONFLICT,
            )
        cohort = assessment.cohort
        if not PSPRegistration.objects.filter(
            user=request.user,
            cohort=cohort,
            status='active',
            psp_tier='100kes',
            amount_expected=100,
        ).exists():
            return Response(
                {'error': 'Verified KSh 100 main contest payment is required before starting this assessment.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if AssessmentAttempt.objects.filter(user=request.user, assessment=assessment).exists():
            return Response({'error': 'Already attempted.'}, status=status.HTTP_400_BAD_REQUEST)
        question_ids = list(assessment.questions.values_list('id', flat=True))
        random.shuffle(question_ids)
        attempt = AssessmentAttempt.objects.create(
            user=request.user,
            assessment=assessment,
            cohort=assessment.cohort,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            question_order=[str(question_id) for question_id in question_ids],
        )
        return Response(AssessmentAttemptSerializer(attempt).data, status=status.HTTP_201_CREATED)


class SubmitAssessmentView(APIView):
    @transaction.atomic
    def post(self, request, assessment_id):
        attempt = get_object_or_404(
            AssessmentAttempt.objects.select_for_update(), assessment_id=assessment_id,
            user=request.user, status='in_progress',
        )
        if timezone.now() > attempt.started_at + timedelta(minutes=attempt.assessment.time_limit_minutes):
            attempt.status = 'submitted'
            attempt.submitted_at = timezone.now()
            attempt.save(update_fields=['status', 'submitted_at'])
            return Response({'error': 'Assessment time has expired.'}, status=status.HTTP_400_BAD_REQUEST)
        answers = request.data.get('answers', {})
        if not isinstance(answers, dict):
            return Response({'error': 'Answers must be submitted as a question-to-answer map.'}, status=status.HTTP_400_BAD_REQUEST)
        allowed_question_ids = set(attempt.question_order)
        attempt.answers = {
            str(question_id): answer
            for question_id, answer in answers.items()
            if str(question_id) in allowed_question_ids
        }
        attempt.submitted_at = timezone.now()
        attempt.status = 'submitted'
        attempt.ip_address = _get_client_ip(request)
        attempt.save()

        result = flag_attempt(str(attempt.id))
        score = _grade(attempt)
        if result['flagged']:
            score = round(max(0, score * (1 - result['penalty_percent'] / 100)), 2)
        attempt.score = score
        attempt.status = 'graded'
        attempt.save(update_fields=['score', 'status'])

        # If score meets threshold, create a mentorship eligibility assignment
        try:
            if score >= 80:
                # skills coach eligibility by default; payout allocation happens elsewhere
                assignment, created = CohortCoachAssignment.objects.get_or_create(
                    cohort=attempt.cohort,
                    user=request.user,
                    role='skills',
                    defaults={'score': score, 'eligibility_status': 'valid', 'allocated_at': timezone.now()},
                )
                if not created:
                    assignment.score = score
                    assignment.eligibility_status = 'valid'
                    assignment.save(update_fields=['score', 'eligibility_status'])

                # notify the user they are eligible for mentorship/opportunities
                try:
                    from apps.notifications.utils import send_notification
                    send_notification(
                        user=request.user,
                        notification_type='system',
                        title='Mentorship eligibility unlocked',
                        message=f'Congratulations — your assessment score of {score}% qualifies you for mentorship opportunities and cohort coach consideration. Check the Mentorship page for next steps.',
                        action_url='/mentorship',
                        metadata={'cohort_id': str(attempt.cohort.id), 'score': score},
                    )
                except Exception:
                    # do not fail grading if notification fails
                    pass
        except Exception:
            # do not fail grading if assignment creation fails
            pass

        # notify the user that mentorship is available (all participants are eligible to request mentorship)
        try:
            from apps.notifications.utils import send_notification
            amount = PSPRegistration.PSP_TIER_AMOUNTS.get(attempt.cohort.payment_tier, 0)
            send_notification(
                user=request.user,
                notification_type='system',
                title='Mentorship available',
                message=f'Your participation has been recorded. To join another {attempt.cohort.get_payment_tier_display()} cohort, pay KES {amount} to Till {PSPRegistration.PAYMENT_TILL_NUMBER}. Mentorship is open to everyone; coaching tracks and payouts are reserved for participants selected through the completed cohort results.',
                action_url='/mentorship',
                metadata={'cohort_id': str(attempt.cohort.id), 'score': score, 'payment_till': PSPRegistration.PAYMENT_TILL_NUMBER, 'payment_amount': str(amount)},
            )
        except Exception:
            pass

        recalculate_trust_score(request.user, reason='Assessment completed')

        return Response({
            'score': score,
            'flagged': result['flagged'],
            'penalty_percent': result['penalty_percent'],
            'message': (
                f"Assessment graded. A reasonable {result['penalty_percent']}% review deduction was applied."
                if result['flagged'] else 'Assessment graded successfully.'
            ),
        })


class CohortLeaderboardView(APIView):
    def get(self, request, cohort_id):
        attempts = (
            AssessmentAttempt.objects
            .filter(cohort_id=cohort_id, status='graded')
            .select_related('user__profile', 'user__trust_score')
            .order_by('-score')[:50]
        )
        data = [
            {
                'rank': i + 1,
                'user_id': str(a.user_id),
                'full_name': getattr(getattr(a.user, 'profile', None), 'full_name', 'N/A'),
                'score': a.score,
                'merit_score': getattr(getattr(a.user, 'trust_score', None), 'overall_merit_score', 0),
            }
            for i, a in enumerate(attempts)
        ]
        return Response(data)


class HeartbeatView(APIView):
    def post(self, request, attempt_id):
        attempt = get_object_or_404(
            AssessmentAttempt, id=attempt_id, user=request.user, status='in_progress'
        )
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data['tab_switch']:
            attempt.tab_switches += 1
        if serializer.validated_data['time_anomaly']:
            attempt.time_anomalies += 1
        attempt.save(update_fields=['tab_switches', 'time_anomalies'])
        return Response({'status': 'ok'})
class PSPRegistrationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PSPRegistration.objects.all().order_by('-created_at') if request.user.is_admin else PSPRegistration.objects.filter(user=request.user).order_by('-created_at')
        status_filter = request.query_params.get('status')
        search = request.query_params.get('q')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(phone_number__icontains=search))
        data = PSPRegistrationSerializer(qs, many=True).data
        return Response(data)

    def post(self, request):
        serializer = PSPRegistrationCreateSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        return Response(
            PSPRegistrationSerializer(serializer.save()).data,
            status=status.HTTP_201_CREATED,
        )


class AllocateCohortRewardsView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, cohort_id):
        try:
            result = allocate_cohort_rewards(cohort_id)
        except Cohort.DoesNotExist:
            return Response({'error': 'Cohort not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'message': 'Coach payouts and cohort wallets allocated successfully.',
            **result,
        }, status=status.HTTP_201_CREATED)


class CoachPayoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        assignments = CohortCoachAssignment.objects.filter(
            user=request.user,
            eligibility_status='valid',
            payout_amount__gt=0,
        ).select_related('cohort').order_by('-allocated_at')
        if not assignments.exists():
            return Response(
                {'error': 'You are not qualified for a coach payout. Complete a cohort and meet the selection criteria first.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(CoachPayoutSerializer(assignments, many=True).data)

    def get(self, request):
        assignments = CohortCoachAssignment.objects.filter(
            user=request.user,
            eligibility_status='valid',
            payout_amount__gt=0,
        ).select_related('cohort').order_by('-allocated_at')
        return Response(CoachPayoutSerializer(assignments, many=True).data)

    def patch(self, request, assignment_id):
        assignment = get_object_or_404(
            CohortCoachAssignment,
            id=assignment_id,
            user=request.user,
            eligibility_status='valid',
            payout_amount__gt=0,
        )
        serializer = CoachPayoutSerializer(assignment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save(
            payout_status='details_submitted',
            payment_details_submitted_at=timezone.now(),
        )
        return Response(CoachPayoutSerializer(assignment).data)


class MentorshipFollowUpView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, cohort_id):
        assignments = CohortCoachAssignment.objects.filter(cohort_id=cohort_id, eligibility_status='valid')
        if not assignments.exists():
            return Response({'error': 'No valid mentorship assignments are available for follow-up.'}, status=status.HTTP_400_BAD_REQUEST)
        groups = {}
        for assignment in assignments:
            groups.setdefault(assignment.role, []).append(assignment)
        averages = {role: sum(float(item.improvement_delta) for item in group) / len(group) for role, group in groups.items()}
        winning_role = max(averages, key=averages.get)
        assignments.update(follow_up_completed=True, deployment_eligible=False)
        assignments.filter(role=winning_role).update(deployment_eligible=True)
        from apps.notifications.utils import send_notification
        for assignment in assignments.filter(role=winning_role):
            send_notification(user=assignment.user, notification_type='system', title='Mentorship follow-up complete', message=f'Your {assignment.get_role_display()} group led the improvement review for this cohort. You are now eligible for deployment consideration and mentor continuation.', action_url='/mentors', metadata={'cohort_id': str(cohort_id), 'deployment_eligible': True})
        return Response({'winning_group': winning_role, 'group_averages': averages, 'deployment_eligible': assignments.filter(role=winning_role).count()})


class WhatsAppInviteRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        requests = WhatsAppInviteRequest.objects.filter(user=request.user).order_by('-created_at')
        return Response(WhatsAppInviteRequestSerializer(requests, many=True).data)

    def post(self, request):
        serializer = WhatsAppInviteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cohort = serializer.validated_data.get('cohort')
        coach_type = serializer.validated_data.get('coach_type', '')
        invite, created = WhatsAppInviteRequest.objects.get_or_create(
            user=request.user,
            cohort=cohort,
            coach_type=coach_type,
            status='pending',
        )
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(WhatsAppInviteRequestSerializer(invite).data, status=response_status)


class WhatsAppInviteReviewView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, request_id):
        invite = get_object_or_404(WhatsAppInviteRequest, id=request_id)
        decision = request.data.get('status')
        if decision not in ('approved', 'rejected'):
            return Response({'error': 'Status must be approved or rejected.'}, status=status.HTTP_400_BAD_REQUEST)
        if decision == 'approved' and not request.data.get('group_link'):
            return Response({'error': 'A WhatsApp group link is required for approval.'}, status=status.HTTP_400_BAD_REQUEST)
        invite.status = decision
        invite.group_link = request.data.get('group_link', '') if decision == 'approved' else ''
        invite.admin_notes = request.data.get('admin_notes', '')
        invite.reviewed_by = request.user
        invite.reviewed_at = timezone.now()
        invite.save(update_fields=['status', 'group_link', 'admin_notes', 'reviewed_by', 'reviewed_at'])
        from apps.notifications.utils import send_notification
        message = (
            f"Your {invite.coach_type or 'mentorship'} WhatsApp invite is approved. Join here: {invite.group_link}"
            if decision == 'approved' else
            f"Your {invite.coach_type or 'mentorship'} WhatsApp invite request was not approved. {invite.admin_notes}".strip()
        )
        send_notification(
            user=invite.user,
            notification_type='system',
            title='WhatsApp mentorship invite update',
            message=message,
            action_url=invite.group_link if decision == 'approved' else '/mentors',
            metadata={'invite_request_id': str(invite.id), 'status': decision},
        )
        return Response(WhatsAppInviteRequestSerializer(invite).data)


class PSPRegistrationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reg_id):
        lookup = {'id': reg_id} if request.user.is_admin else {'id': reg_id, 'user': request.user}
        reg = get_object_or_404(PSPRegistration, **lookup)
        return Response(PSPRegistrationSerializer(reg).data)


class PSPVerifyView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, reg_id):
        reg = get_object_or_404(PSPRegistration, id=reg_id)
        amount = request.data.get('amount_received')
        payment_ref = request.data.get('payment_reference')
        notes = request.data.get('notes', '')

        try:
            amount_val = float(amount)
        except Exception:
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)

        # create verification record
        ver = PSPVerification.objects.create(
            registration=reg,
            verified_by=request.user,
            amount_received=amount_val,
            payment_reference=payment_ref,
            notes=notes,
        )

        # decide status
        if abs(float(reg.amount_expected) - amount_val) < 0.01:
            reg.status = 'confirmed'
            reg.save(update_fields=['status'])
            # enroll user into cohort if present
            if reg.cohort:
                CohortEnrollment.objects.get_or_create(user=reg.user, cohort=reg.cohort)
                reg.status = 'active'
                reg.save(update_fields=['status'])
        else:
            reg.status = 'failed'
            reg.save(update_fields=['status'])

        return Response(PSPVerificationSerializer(ver).data, status=status.HTTP_201_CREATED)


def _grade(attempt: AssessmentAttempt) -> float:
    questions_by_id = {
        str(question.id): question
        for question in attempt.assessment.questions.all()
    }
    questions = [
        questions_by_id[question_id]
        for question_id in attempt.question_order
        if question_id in questions_by_id
    ]
    if not questions:
        return 0.0
    total_points = sum(q.points for q in questions)
    earned = sum(
        q.points for q in questions
        if (attempt.answers or {}).get(str(q.id)) == q.correct_answer
    )
    return round((earned / total_points) * 100, 2) if total_points else 0.0


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0]
    return request.META.get('REMOTE_ADDR')
