import csv

from django.http import FileResponse
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin, IsApprovedVendor
from apps.fraud.models import AuditLog
from apps.notifications.utils import send_notification
from utils.pagination import StandardResultsPagination

from .models import (
    CampaignApproval,
    CampaignAsset,
    CampaignEvent,
    SponsorshipCampaign,
    VendorProfile,
    VendorVerification,
)
from .serializers import (
    AdminCampaignSerializer,
    AdminVendorDecisionSerializer,
    AdminVendorProfileSerializer,
    AdminVendorVerificationDecisionSerializer,
    CampaignAssetSerializer,
    CampaignDecisionSerializer,
    CampaignEventInputSerializer,
    SponsorshipCampaignSerializer,
    VendorProfileSerializer,
    VendorVerificationSerializer,
)


MINIMUM_REPORT_AUDIENCE = 5
CAMPAIGN_STATES = {
    'draft', 'pending_approval', 'approved', 'active', 'paused',
    'cancellation_requested', 'cancelled', 'completed', 'rejected',
    'changes_requested',
}


def _audit(request, action, model_name, object_id, changes):
    AuditLog.objects.create(
        user=request.user,
        action=action,
        model_name=model_name,
        object_id=str(object_id),
        changes=changes,
        ip_address=request.META.get('REMOTE_ADDR'),
    )


def _notify_after_commit(user, title, message):
    transaction.on_commit(
        lambda user=user, title=title, message=message: send_notification(
            user,
            'system',
            title,
            message,
            action_url='/vendor',
        )
    )


def _record_event(campaign, event_type, *, user, deduplication_key, source='platform'):
    try:
        CampaignEvent.objects.get_or_create(
            campaign=campaign,
            deduplication_key=deduplication_key,
            defaults={
                'event_type': event_type,
                'user': user,
                'source': source,
                'occurred_at': timezone.now(),
            },
        )
    except IntegrityError:
        if not CampaignEvent.objects.filter(
            campaign=campaign,
            deduplication_key=deduplication_key,
        ).exists():
            raise


def record_tutorial_campaign_event(user, tutorial, event_type):
    if event_type not in {'lesson_start', 'lesson_completion', 'assessment_completion'}:
        raise ValueError('Unsupported platform campaign event.')
    today = timezone.localdate()
    campaigns = SponsorshipCampaign.objects.filter(
        status='active',
        start_date__lte=today,
        end_date__gte=today,
        vendor__status='approved',
    ).filter(Q(study_area=tutorial.field) | Q(campaign_type__in=('tutorial', 'learning_initiative')))
    for campaign in campaigns:
        if campaign.target_content_ids and str(tutorial.id) not in campaign.target_content_ids:
            if campaign.study_area != tutorial.field:
                continue
        deduplication_key = f'{event_type}:{user.pk}:{tutorial.pk}'
        _record_event(
            campaign,
            event_type,
            user=user,
            deduplication_key=deduplication_key,
        )


def contest_sponsor_attributions(assessments):
    today = timezone.localdate()
    campaigns = SponsorshipCampaign.objects.filter(
        status='active',
        campaign_type='contest',
        start_date__lte=today,
        end_date__gte=today,
        vendor__status='approved',
    ).select_related('vendor')
    attributions = {}
    for campaign in campaigns:
        targets = set(campaign.target_content_ids)
        for assessment in assessments:
            assessment_id = str(assessment.id)
            if targets and assessment_id not in targets:
                continue
            if not targets and campaign.study_area and campaign.study_area != assessment.field:
                continue
            attributions.setdefault(assessment_id, []).append({
                'sponsor_name': campaign.vendor.business_name,
                'sponsor_disclosure': campaign.sponsor_disclosure,
                'eligibility_rules': campaign.eligibility_rules,
            })
    return attributions


def record_contest_campaign_event(user, assessment):
    today = timezone.localdate()
    campaigns = SponsorshipCampaign.objects.filter(
        status='active',
        campaign_type='contest',
        start_date__lte=today,
        end_date__gte=today,
        vendor__status='approved',
    )
    for campaign in campaigns:
        targets = campaign.target_content_ids
        if targets and str(assessment.id) not in targets:
            continue
        if not targets and campaign.study_area and campaign.study_area != assessment.field:
            continue
        _record_event(
            campaign,
            'assessment_completion',
            user=user,
            deduplication_key=f'assessment_completion:{user.pk}:{assessment.pk}',
        )


class VendorOnboardingView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get(self, request):
        profile = VendorProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({'detail': 'Vendor onboarding has not been submitted.'}, status=404)
        return Response(VendorProfileSerializer(profile).data)

    def post(self, request):
        if request.user.is_admin:
            return Response({'detail': 'Administrator accounts cannot be converted to vendor accounts.'}, status=403)
        profile = VendorProfile.objects.filter(user=request.user).first()
        if profile and profile.status not in {'rejected'}:
            return Response({'detail': 'A vendor application already exists.'}, status=400)
        serializer = VendorProfileSerializer(profile, data=request.data, partial=profile is not None)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            vendor = serializer.save(
                user=request.user,
                status='pending',
                admin_feedback='',
                reviewed_by=None,
                reviewed_at=None,
            )
            if request.user.role != 'vendor':
                request.user.role = 'vendor'
                request.user.save(update_fields=('role',))
            _audit(
                request,
                'vendor_application_submitted',
                'VendorProfile',
                vendor.id,
                {'status': {'to': 'pending'}},
            )
            _notify_after_commit(
                request.user,
                'Vendor application received',
                'Your vendor application is pending administrative review.',
            )
        return Response(VendorProfileSerializer(vendor).data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        profile = get_object_or_404(VendorProfile, user=request.user)
        if profile.status not in {'pending', 'rejected'}:
            return Response({'detail': 'Only pending or rejected vendor profiles can be edited.'}, status=400)
        serializer = VendorProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            profile = serializer.save(status='pending', admin_feedback='', reviewed_by=None, reviewed_at=None)
            _audit(
                request,
                'vendor_application_updated',
                'VendorProfile',
                profile.id,
                {'fields': sorted(serializer.validated_data.keys()), 'status': 'pending'},
            )
        return Response(VendorProfileSerializer(profile).data)


class VendorVerificationListCreateView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        profile = get_object_or_404(VendorProfile, user=request.user)
        return Response(VendorVerificationSerializer(profile.verifications.all(), many=True).data)

    def post(self, request):
        profile = get_object_or_404(VendorProfile, user=request.user)
        if profile.status == 'suspended':
            return Response({'detail': 'Suspended vendor profiles cannot submit documents.'}, status=403)
        serializer = VendorVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = serializer.save(vendor=profile)
        _audit(
            request,
            'vendor_verification_document_submitted',
            'VendorVerification',
            verification.id,
            {'status': {'to': 'pending'}},
        )
        return Response(VendorVerificationSerializer(verification).data, status=status.HTTP_201_CREATED)


class VendorCampaignListCreateView(APIView):
    permission_classes = (IsApprovedVendor,)

    def get(self, request):
        profile = request.user.vendor_profile
        queryset = SponsorshipCampaign.objects.filter(vendor=profile).prefetch_related('assets', 'review_history')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request)
        for campaign in page:
            campaign.sync_completion_status()
        return paginator.get_paginated_response(SponsorshipCampaignSerializer(page, many=True).data)

    def post(self, request):
        serializer = SponsorshipCampaignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            campaign = serializer.save(vendor=request.user.vendor_profile)
            _audit(
                request,
                'campaign_draft_created',
                'SponsorshipCampaign',
                campaign.id,
                {'status': campaign.status, 'fields': sorted(serializer.validated_data.keys())},
            )
        return Response(SponsorshipCampaignSerializer(campaign).data, status=status.HTTP_201_CREATED)


class VendorCampaignDetailView(APIView):
    permission_classes = (IsApprovedVendor,)

    def get_campaign(self, request, campaign_id):
        campaign = get_object_or_404(
            SponsorshipCampaign.objects.prefetch_related('assets', 'review_history'),
            id=campaign_id,
            vendor=request.user.vendor_profile,
        )
        campaign.sync_completion_status()
        return campaign

    def get(self, request, campaign_id):
        campaign = self.get_campaign(request, campaign_id)
        return Response(SponsorshipCampaignSerializer(campaign).data)

    def patch(self, request, campaign_id):
        campaign = self.get_campaign(request, campaign_id)
        if campaign.status not in {'draft', 'rejected', 'changes_requested'}:
            return Response({'detail': 'Only draft, rejected, or changes-requested campaigns can be edited.'}, status=400)
        serializer = SponsorshipCampaignSerializer(campaign, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            old_status = campaign.status
            if campaign.status in {'rejected', 'changes_requested'}:
                campaign.status = 'draft'
                campaign.admin_feedback = ''
                campaign.reviewed_by = None
                campaign.reviewed_at = None
            campaign = serializer.save()
            _audit(
                request,
                'campaign_draft_updated',
                'SponsorshipCampaign',
                campaign.id,
                {'status': {'from': old_status, 'to': campaign.status}, 'fields': sorted(serializer.validated_data.keys())},
            )
        return Response(SponsorshipCampaignSerializer(campaign).data)


class VendorCampaignSubmitView(APIView):
    permission_classes = (IsApprovedVendor,)

    def post(self, request, campaign_id):
        with transaction.atomic():
            campaign = get_object_or_404(
                SponsorshipCampaign.objects.select_for_update(),
                id=campaign_id,
                vendor=request.user.vendor_profile,
            )
            if campaign.status not in {'draft', 'rejected', 'changes_requested'}:
                return Response({'detail': 'Only draft, rejected, or changes-requested campaigns can be submitted.'}, status=400)
            if not campaign.sponsor_disclosure.strip():
                return Response({'sponsor_disclosure': 'A clear sponsorship disclosure is required.'}, status=400)
            if campaign.end_date < timezone.localdate():
                return Response({'end_date': 'The campaign end date must not be in the past.'}, status=400)
            campaign.status = 'pending_approval'
            campaign.submitted_at = timezone.now()
            campaign.admin_feedback = ''
            campaign.reviewed_by = None
            campaign.reviewed_at = None
            campaign.save(update_fields=(
                'status', 'submitted_at', 'admin_feedback', 'reviewed_by',
                'reviewed_at', 'updated_at',
            ))
            CampaignApproval.objects.create(
                campaign=campaign,
                actor=request.user,
                decision='submitted',
            )
            _audit(request, 'campaign_submitted', 'SponsorshipCampaign', campaign.id, {'status': {'to': 'pending_approval'}})
        return Response(SponsorshipCampaignSerializer(campaign).data)


class VendorCampaignActionView(APIView):
    permission_classes = (IsApprovedVendor,)

    def post(self, request, campaign_id):
        action = serializers.ChoiceField(choices=('pause', 'request_cancellation')).run_validation(
            request.data.get('action'),
        )
        with transaction.atomic():
            campaign = get_object_or_404(
                SponsorshipCampaign.objects.select_for_update(),
                id=campaign_id,
                vendor=request.user.vendor_profile,
            )
            if action == 'pause' and campaign.status == 'active':
                campaign.status = 'paused'
                decision = 'paused'
            elif action == 'request_cancellation' and campaign.status in {'active', 'paused'}:
                campaign.status = 'cancellation_requested'
                decision = 'cancellation_requested'
            else:
                return Response({'detail': 'This action is not available for the campaign status.'}, status=400)
            campaign.save(update_fields=('status', 'updated_at'))
            CampaignApproval.objects.create(
                campaign=campaign,
                actor=request.user,
                decision=decision,
            )
            _audit(request, f'campaign_{decision}', 'SponsorshipCampaign', campaign.id, {'status': {'to': campaign.status}})
        return Response(SponsorshipCampaignSerializer(campaign).data)


class VendorCampaignAssetView(APIView):
    permission_classes = (IsApprovedVendor,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, campaign_id):
        campaign = get_object_or_404(
            SponsorshipCampaign,
            id=campaign_id,
            vendor=request.user.vendor_profile,
            status__in=('draft', 'rejected', 'changes_requested'),
        )
        serializer = CampaignAssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            asset = serializer.save(campaign=campaign, uploaded_by=request.user)
            _audit(
                request,
                'campaign_asset_uploaded',
                'CampaignAsset',
                asset.id,
                {'campaign_id': str(campaign.id), 'description': asset.description},
            )
        return Response(CampaignAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class VendorCampaignDashboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        profile = VendorProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({'detail': 'Complete vendor onboarding to access the vendor dashboard.'}, status=403)
        campaigns = SponsorshipCampaign.objects.filter(vendor=profile)
        counts = {state: campaigns.filter(status=state).count() for state in CAMPAIGN_STATES}
        return Response({
            'profile': VendorProfileSerializer(profile).data,
            'campaigns_by_status': counts,
            'campaign_count': campaigns.count(),
            'proposed_budget': campaigns.aggregate(total=Sum('budget_amount'))['total'] or 0,
            'approved_budget': campaigns.aggregate(total=Sum('approved_budget_amount'))['total'] or 0,
            'recorded_spending': 0,
            'billing_enabled': False,
            'billing_note': 'No sponsorship payment provider is configured; no real spending is processed or reported.',
        })


class ActiveCampaignListView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        today = timezone.localdate()
        campaigns = SponsorshipCampaign.objects.filter(
            status='active',
            start_date__lte=today,
            end_date__gte=today,
            vendor__status='approved',
        ).select_related('vendor').order_by('-start_date')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(campaigns, request)
        if request.user.is_authenticated:
            for campaign in page:
                if request.user.pk != campaign.vendor.user_id:
                    _record_event(
                        campaign,
                        'view',
                        user=request.user,
                        deduplication_key=f'view:{request.user.pk}',
                    )
        return paginator.get_paginated_response([{
            'id': str(campaign.id),
            'name': campaign.name,
            'description': campaign.description,
            'objectives': campaign.objectives,
            'campaign_type': campaign.campaign_type,
            'study_area': campaign.study_area,
            'eligibility_rules': campaign.eligibility_rules,
            'sponsor_name': campaign.vendor.business_name,
            'sponsor_disclosure': campaign.sponsor_disclosure,
            'start_date': campaign.start_date,
            'end_date': campaign.end_date,
        } for campaign in page])


class CampaignClickEventView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, campaign_id):
        serializer = CampaignEventInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = get_object_or_404(
            SponsorshipCampaign.objects.select_related('vendor'),
            id=campaign_id,
            status='active',
            vendor__status='approved',
            start_date__lte=timezone.localdate(),
            end_date__gte=timezone.localdate(),
        )
        if request.user.pk == campaign.vendor.user_id:
            return Response({'detail': 'Vendor activity is not counted as campaign engagement.'}, status=403)
        _record_event(
            campaign,
            'click',
            user=request.user,
            deduplication_key=f'click:{request.user.pk}',
            source='authenticated_click',
        )
        return Response({'recorded': True})


def _report_data(campaign):
    events = CampaignEvent.objects.filter(campaign=campaign, user__isnull=False)
    audience = events.filter(event_type='view').values('user_id').distinct().count()
    if audience < MINIMUM_REPORT_AUDIENCE:
        return {
            'campaign_id': str(campaign.id),
            'campaign_name': campaign.name,
            'status': campaign.status,
            'start_date': campaign.start_date,
            'end_date': campaign.end_date,
            'privacy_threshold': MINIMUM_REPORT_AUDIENCE,
            'suppressed': True,
            'suppression_note': 'Aggregated metrics are hidden until at least five authenticated viewers are recorded.',
        }
    metrics = events.values('event_type').annotate(total=Count('id'), unique_users=Count('user_id', distinct=True))
    grouped = {row['event_type']: row for row in metrics}
    activity_by_day = events.annotate(day=TruncDate('occurred_at')).values(
        'day', 'event_type',
    ).annotate(
        total=Count('id'),
        unique_users=Count('user_id', distinct=True),
    ).filter(
        unique_users__gte=MINIMUM_REPORT_AUDIENCE,
    ).order_by('day', 'event_type')
    unique_views = grouped.get('view', {}).get('unique_users', 0)
    clicks = grouped.get('click', {}).get('total', 0)
    lesson_starts = grouped.get('lesson_start', {}).get('total', 0)
    lesson_completions = grouped.get('lesson_completion', {}).get('total', 0)
    assessment_completions = grouped.get('assessment_completion', {}).get('total', 0)
    return {
        'campaign_id': str(campaign.id),
        'campaign_name': campaign.name,
        'status': campaign.status,
        'start_date': campaign.start_date,
        'end_date': campaign.end_date,
        'privacy_threshold': MINIMUM_REPORT_AUDIENCE,
        'suppressed': False,
        'recorded_authenticated_unique_views': unique_views,
        'recorded_click_events': clicks,
        'recorded_lesson_starts': lesson_starts,
        'recorded_lesson_completions': lesson_completions,
        'recorded_assessment_completions': assessment_completions,
        'recorded_activity_by_day': [{
            'date': row['day'],
            'event_type': row['event_type'],
            'count': row['total'],
        } for row in activity_by_day],
        'click_through_rate': round(clicks / unique_views, 4) if unique_views else None,
        'lesson_completion_per_viewer_rate': round(lesson_completions / unique_views, 4) if unique_views else None,
        'assessment_completion_per_viewer_rate': round(assessment_completions / unique_views, 4) if unique_views else None,
        'metric_disclaimer': 'Counts are deduplicated platform-recorded activity, not independently verified user outcomes.',
    }


class VendorCampaignReportView(APIView):
    permission_classes = (IsApprovedVendor,)

    def get_campaign(self, request, campaign_id):
        campaign = get_object_or_404(
            SponsorshipCampaign,
            id=campaign_id,
            vendor=request.user.vendor_profile,
        )
        campaign.sync_completion_status()
        return campaign

    def get(self, request, campaign_id):
        return Response(_report_data(self.get_campaign(request, campaign_id)))


class VendorCampaignReportCsvView(VendorCampaignReportView):
    def get(self, request, campaign_id):
        data = _report_data(self.get_campaign(request, campaign_id))
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="campaign-{campaign_id}-report.csv"'
        writer = csv.writer(response)
        writer.writerow(('Metric', 'Value', 'Date', 'Event type', 'Recorded count'))
        for key, value in data.items():
            if key == 'recorded_activity_by_day':
                for row in value:
                    writer.writerow((key, '', row['date'], row['event_type'], row['count']))
                continue
            writer.writerow((key, value if value is not None else '', '', '', ''))
        return response


class AdminVendorListView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        queryset = VendorProfile.objects.select_related('user', 'reviewed_by').prefetch_related('verifications')
        vendor_status = request.query_params.get('status')
        if vendor_status:
            if vendor_status not in {value for value, _label in VendorProfile.STATUS_CHOICES}:
                raise serializers.ValidationError({'status': 'Choose a valid vendor status.'})
            queryset = queryset.filter(status=vendor_status)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset.order_by('-created_at'), request)
        return paginator.get_paginated_response(AdminVendorProfileSerializer(page, many=True).data)


class AdminVendorDecisionView(APIView):
    permission_classes = (IsAdmin,)

    def post(self, request, vendor_id):
        serializer = AdminVendorDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data['status']
        feedback = serializer.validated_data.get('feedback', '')
        with transaction.atomic():
            vendor = get_object_or_404(VendorProfile.objects.select_for_update(), id=vendor_id)
            old_status = vendor.status
            if decision == 'approved':
                if vendor.status not in {'pending', 'rejected'}:
                    return Response({'detail': 'Only pending or rejected vendors can be approved.'}, status=400)
                vendor.status = 'approved'
            elif decision == 'rejected':
                if vendor.status != 'pending':
                    return Response({'detail': 'Only pending vendor applications can be rejected.'}, status=400)
                vendor.status = 'rejected'
            elif decision == 'suspended':
                if vendor.status != 'approved':
                    return Response({'detail': 'Only approved vendors can be suspended.'}, status=400)
                vendor.status = 'suspended'
            else:
                if vendor.status != 'suspended':
                    return Response({'detail': 'Only suspended vendors can be reactivated.'}, status=400)
                vendor.status = 'approved'
            vendor.admin_feedback = feedback
            vendor.reviewed_by = request.user
            vendor.reviewed_at = timezone.now()
            vendor.save(update_fields=('status', 'admin_feedback', 'reviewed_by', 'reviewed_at', 'updated_at'))
            if vendor.status == 'suspended':
                active_campaigns = vendor.campaigns.select_for_update().filter(status='active')
                for campaign in active_campaigns:
                    campaign.status = 'paused'
                    campaign.admin_feedback = 'Automatically paused because the vendor account was suspended.'
                    campaign.reviewed_by = request.user
                    campaign.reviewed_at = timezone.now()
                    campaign.save(update_fields=(
                        'status', 'admin_feedback', 'reviewed_by', 'reviewed_at', 'updated_at',
                    ))
                    CampaignApproval.objects.create(
                        campaign=campaign,
                        actor=request.user,
                        decision='paused',
                        feedback=campaign.admin_feedback,
                    )
                    _audit(
                        request,
                        'campaign_paused_vendor_suspended',
                        'SponsorshipCampaign',
                        campaign.id,
                        {'status': {'from': 'active', 'to': 'paused'}, 'vendor_id': str(vendor.id)},
                    )
            _audit(
                request,
                'vendor_status_changed',
                'VendorProfile',
                vendor.id,
                {'status': {'from': old_status, 'to': vendor.status}, 'feedback': feedback},
            )
            _notify_after_commit(
                vendor.user,
                'Vendor account status updated',
                f'Your vendor account is now {vendor.status}. Review the vendor workspace for administrative feedback.',
            )
        return Response(AdminVendorProfileSerializer(vendor).data)


class AdminVendorVerificationDecisionView(APIView):
    permission_classes = (IsAdmin,)

    def post(self, request, verification_id):
        serializer = AdminVendorVerificationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            verification = get_object_or_404(
                VendorVerification.objects.select_for_update().select_related('vendor'),
                id=verification_id,
            )
            if verification.status != 'pending':
                return Response({'detail': 'Only pending verification documents can be reviewed.'}, status=400)
            verification.status = serializer.validated_data['status']
            verification.admin_feedback = serializer.validated_data.get('feedback', '')
            verification.reviewed_by = request.user
            verification.reviewed_at = timezone.now()
            verification.save(update_fields=('status', 'admin_feedback', 'reviewed_by', 'reviewed_at'))
            _audit(
                request,
                'vendor_verification_reviewed',
                'VendorVerification',
                verification.id,
                {'status': verification.status, 'feedback': verification.admin_feedback},
            )
            _notify_after_commit(
                verification.vendor.user,
                'Verification document reviewed',
                f'Your {verification.document_type} document was {verification.status}. Review the vendor workspace for feedback.',
            )
        return Response(VendorVerificationSerializer(verification).data)


class AdminVendorVerificationDocumentView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request, verification_id):
        verification = get_object_or_404(
            VendorVerification.objects.select_related('vendor'),
            id=verification_id,
        )
        if not verification.document:
            return Response({'detail': 'No verification document is available.'}, status=404)
        _audit(
            request,
            'vendor_verification_document_downloaded',
            'VendorVerification',
            verification.id,
            {'vendor_id': str(verification.vendor_id)},
        )
        safe_name = verification.document.name.rsplit('/', 1)[-1]
        return FileResponse(
            verification.document.open('rb'),
            as_attachment=True,
            filename=safe_name,
            content_type='application/octet-stream',
        )


class AdminCampaignListView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        queryset = SponsorshipCampaign.objects.select_related('vendor', 'reviewed_by').prefetch_related(
            'assets', 'review_history__actor',
        )
        campaign_status = request.query_params.get('status')
        if campaign_status:
            if campaign_status not in CAMPAIGN_STATES:
                raise serializers.ValidationError({'status': 'Choose a valid campaign status.'})
            queryset = queryset.filter(status=campaign_status)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset.order_by('-submitted_at', '-created_at'), request)
        for campaign in page:
            campaign.sync_completion_status()
        return paginator.get_paginated_response(AdminCampaignSerializer(page, many=True).data)


class AdminCampaignDecisionView(APIView):
    permission_classes = (IsAdmin,)

    def post(self, request, campaign_id):
        serializer = CampaignDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        decision = values['decision']

        with transaction.atomic():
            campaign = get_object_or_404(
                SponsorshipCampaign.objects.select_for_update().select_related('vendor'),
                id=campaign_id,
            )
            old_status = campaign.status
            if decision in {'approve', 'reject', 'changes_requested'}:
                if campaign.status != 'pending_approval':
                    return Response({'detail': 'Only pending campaigns can be reviewed.'}, status=400)
                if campaign.vendor.status != 'approved':
                    return Response({'detail': 'The vendor must be approved before its campaign.'}, status=400)
                if decision == 'approve':
                    if not campaign.sponsor_disclosure.strip():
                        return Response({'sponsor_disclosure': 'A sponsor disclosure is required.'}, status=400)
                    if campaign.end_date < timezone.localdate():
                        return Response(
                            {'end_date': 'The campaign dates have expired; request updated dates before approving.'},
                            status=400,
                        )
                    campaign.status = 'active' if campaign.start_date <= timezone.localdate() <= campaign.end_date else 'approved'
                    campaign.approved_budget_amount = values.get('approved_budget_amount', campaign.budget_amount)
                    if (
                        campaign.approved_budget_amount is not None
                        and (
                            campaign.budget_amount is None
                            or campaign.approved_budget_amount > campaign.budget_amount
                        )
                    ):
                        return Response(
                            {'approved_budget_amount': 'An approved budget must not exceed a vendor-proposed amount.'},
                            status=400,
                        )
                    campaign.budget_tracking_enabled = False
                elif decision == 'reject':
                    campaign.status = 'rejected'
                else:
                    campaign.status = 'changes_requested'
            elif decision == 'activate':
                if campaign.status != 'approved':
                    return Response({'detail': 'Only approved future campaigns can be activated.'}, status=400)
                if not campaign.start_date <= timezone.localdate() <= campaign.end_date:
                    return Response({'detail': 'The campaign is outside its approved active dates.'}, status=400)
                campaign.status = 'active'
            elif decision == 'resume':
                if campaign.status != 'paused' or campaign.vendor.status != 'approved':
                    return Response({'detail': 'Only campaigns paused for an approved vendor can be resumed.'}, status=400)
                if not campaign.start_date <= timezone.localdate() <= campaign.end_date:
                    campaign.status = 'completed' if campaign.end_date < timezone.localdate() else 'approved'
                    if campaign.status != 'approved':
                        return Response({'detail': 'The campaign has ended and cannot be resumed.'}, status=400)
                else:
                    campaign.status = 'active'
            elif decision == 'confirm_cancellation':
                if campaign.status != 'cancellation_requested':
                    return Response({'detail': 'There is no pending cancellation request.'}, status=400)
                campaign.status = 'cancelled'
            elif decision == 'deny_cancellation':
                if campaign.status != 'cancellation_requested':
                    return Response({'detail': 'There is no pending cancellation request.'}, status=400)
                campaign.status = 'paused'
            campaign.admin_feedback = values.get('feedback', '')
            campaign.reviewed_by = request.user
            campaign.reviewed_at = timezone.now()
            campaign.save(update_fields=(
                'status', 'approved_budget_amount', 'budget_tracking_enabled',
                'admin_feedback', 'reviewed_by', 'reviewed_at', 'updated_at',
            ))
            history_decision = {
                'approve': 'approved',
                'reject': 'rejected',
                'changes_requested': 'changes_requested',
                'activate': 'activated',
                'resume': 'resumed',
                'confirm_cancellation': 'cancellation_approved',
                'deny_cancellation': 'cancellation_denied',
            }[decision]
            CampaignApproval.objects.create(
                campaign=campaign,
                actor=request.user,
                decision=history_decision,
                feedback=campaign.admin_feedback,
            )
            _audit(
                request,
                f'campaign_{decision}',
                'SponsorshipCampaign',
                campaign.id,
                {
                    'status': {'from': old_status, 'to': campaign.status},
                    'approved_budget_amount': str(campaign.approved_budget_amount) if campaign.approved_budget_amount is not None else None,
                    'budget_tracking_enabled': campaign.budget_tracking_enabled,
                    'feedback': campaign.admin_feedback,
                },
            )
            _notify_after_commit(
                campaign.vendor.user,
                'Campaign status updated',
                f'Your campaign "{campaign.name}" is now {campaign.status.replace("_", " ")}. Review the vendor workspace for administrative feedback.',
            )
        return Response(AdminCampaignSerializer(campaign).data)
