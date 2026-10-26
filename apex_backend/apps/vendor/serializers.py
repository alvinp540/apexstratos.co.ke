import json
from decimal import Decimal

from rest_framework import serializers
import json

from .models import (
    CampaignAsset,
    CampaignApproval,
    SponsorshipCampaign,
    VendorJob,
    VendorProfile,
    VendorRating,
    VendorVerification,
)


def validate_upload_signature(value):
    signature = value.read(16)
    value.seek(0)
    mime_type = value.content_type
    valid = (
        mime_type == 'application/pdf' and signature.startswith(b'%PDF-')
        or mime_type == 'image/jpeg' and signature.startswith(b'\xff\xd8\xff')
        or mime_type == 'image/png' and signature.startswith(b'\x89PNG\r\n\x1a\n')
        or mime_type == 'image/webp' and signature.startswith(b'RIFF') and signature[8:12] == b'WEBP'
    )
    if not valid:
        raise serializers.ValidationError('The file content must match a PDF, JPEG, PNG, or WebP file.')


class VendorVerificationSerializer(serializers.ModelSerializer):
    document = serializers.FileField(write_only=True)
    has_document = serializers.SerializerMethodField()

    class Meta:
        model = VendorVerification
        fields = (
            'id', 'document_type', 'document', 'has_document', 'status', 'admin_feedback',
            'reviewed_at', 'created_at',
        )
        read_only_fields = ('id', 'status', 'admin_feedback', 'reviewed_at', 'created_at')

    def get_has_document(self, verification):
        return bool(verification.document)

    def validate_document(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('Verification documents must be 10 MB or smaller.')
        if value.content_type not in {
            'application/pdf', 'image/jpeg', 'image/png', 'image/webp',
        }:
            raise serializers.ValidationError('Verification documents must be a PDF, JPEG, PNG, or WebP file.')
        validate_upload_signature(value)
        return value


class VendorProfileSerializer(serializers.ModelSerializer):
    verifications = VendorVerificationSerializer(many=True, read_only=True)

    class Meta:
        model = VendorProfile
        fields = (
            'id', 'business_name', 'description', 'category', 'contact_name',
            'contact_email', 'contact_phone', 'website', 'location', 'logo',
            'status', 'admin_feedback', 'reviewed_at', 'created_at', 'updated_at',
            'verifications',
        )
        read_only_fields = ('id', 'status', 'admin_feedback', 'reviewed_at', 'created_at', 'updated_at')

    def validate_logo(self, value):
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Logos must be 5 MB or smaller.')
        return value


class AdminVendorProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    verifications = VendorVerificationSerializer(many=True, read_only=True)

    class Meta:
        model = VendorProfile
        fields = (
            'id', 'email', 'username', 'business_name', 'description', 'category',
            'contact_name', 'contact_email', 'contact_phone', 'website', 'location',
            'logo', 'status', 'admin_feedback', 'reviewed_at', 'created_at', 'verifications',
        )
        read_only_fields = fields


class VendorJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorJob
        fields = (
            'id', 'title', 'description', 'profession_required', 'skills_required',
            'budget_min', 'budget_max', 'currency', 'deadline', 'priority',
            'status', 'min_trust_score', 'evidence_urls', 'location_preference',
            'assigned_professional', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'status', 'assigned_professional', 'created_at', 'updated_at')


class VendorRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorRating
        fields = (
            'id', 'quality_score', 'communication_score',
            'timeliness_score', 'overall_score', 'comment',
        )

    def validate(self, attrs):
        for field in ('quality_score', 'communication_score', 'timeliness_score'):
            if not (1 <= attrs[field] <= 5):
                raise serializers.ValidationError({field: 'Score must be between 1 and 5.'})
        attrs['overall_score'] = round(
            (attrs['quality_score'] + attrs['communication_score'] + attrs['timeliness_score']) / 3, 2
        )
        return attrs


class CampaignAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignAsset
        fields = ('id', 'file', 'description', 'created_at')
        read_only_fields = ('id', 'created_at')

    def validate_file(self, value):
        if value.size > 15 * 1024 * 1024:
            raise serializers.ValidationError('Campaign assets must be 15 MB or smaller.')
        if value.content_type not in {
            'image/jpeg', 'image/png', 'image/webp', 'application/pdf',
        }:
            raise serializers.ValidationError('Campaign assets must be a JPEG, PNG, WebP image, or PDF.')
        validate_upload_signature(value)
        return value


class SponsorshipCampaignSerializer(serializers.ModelSerializer):
    assets = CampaignAssetSerializer(many=True, read_only=True)
    review_history = serializers.SerializerMethodField()

    class Meta:
        model = SponsorshipCampaign
        fields = (
            'id', 'name', 'objectives', 'target_audience', 'campaign_type',
            'eligibility_rules', 'study_area', 'target_content_ids', 'description', 'sponsor_disclosure',
            'start_date', 'end_date', 'target_views', 'budget_amount', 'currency',
            'approved_budget_amount', 'budget_tracking_enabled', 'status', 'admin_feedback', 'submitted_at',
            'reviewed_at', 'created_at', 'updated_at', 'assets', 'review_history',
        )
        read_only_fields = (
            'id', 'approved_budget_amount', 'budget_tracking_enabled', 'status', 'admin_feedback',
            'submitted_at', 'reviewed_at', 'created_at', 'updated_at',
        )

    def validate(self, attrs):
        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end_date = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({'end_date': 'End date must be on or after start date.'})
        if attrs.get('currency', getattr(self.instance, 'currency', 'KES')) != 'KES':
            raise serializers.ValidationError({'currency': 'Campaign budgets currently support KES only.'})
        targets = attrs.get('target_content_ids', getattr(self.instance, 'target_content_ids', []))
        if not isinstance(targets, list) or len(targets) > 100:
            raise serializers.ValidationError({'target_content_ids': 'Provide a list of at most 100 content IDs.'})
        if any(not isinstance(target, str) or len(target) > 80 for target in targets):
            raise serializers.ValidationError({'target_content_ids': 'Each content ID must be text up to 80 characters.'})
        eligibility_rules = attrs.get('eligibility_rules', getattr(self.instance, 'eligibility_rules', {}))
        if not isinstance(eligibility_rules, dict) or len(eligibility_rules) > 20:
            raise serializers.ValidationError({'eligibility_rules': 'Provide an object with at most 20 rule fields.'})
        try:
            encoded_rules = json.dumps(eligibility_rules, ensure_ascii=True)
        except (TypeError, ValueError, RecursionError):
            raise serializers.ValidationError({'eligibility_rules': 'Eligibility rules must contain valid JSON data.'})
        if len(encoded_rules) > 5000:
            raise serializers.ValidationError({'eligibility_rules': 'Eligibility rules must be 5,000 characters or fewer.'})
        return attrs

    def get_review_history(self, campaign):
        return VendorCampaignHistorySerializer(campaign.review_history.all(), many=True).data


class AdminCampaignSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    vendor_status = serializers.CharField(source='vendor.status', read_only=True)
    assets = CampaignAssetSerializer(many=True, read_only=True)
    review_history = serializers.SerializerMethodField()

    class Meta:
        model = SponsorshipCampaign
        fields = (
            'id', 'vendor_name', 'vendor_status', 'name', 'objectives',
            'target_audience', 'campaign_type', 'study_area', 'target_content_ids',
            'eligibility_rules',
            'description', 'sponsor_disclosure', 'start_date', 'end_date',
            'target_views', 'budget_amount', 'currency', 'budget_tracking_enabled',
            'approved_budget_amount', 'status', 'admin_feedback', 'submitted_at', 'reviewed_at', 'created_at',
            'assets', 'review_history',
        )
        read_only_fields = fields

    def get_review_history(self, campaign):
        return CampaignApprovalSerializer(campaign.review_history.all(), many=True).data


class CampaignApprovalSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = CampaignApproval
        fields = ('decision', 'feedback', 'actor_email', 'created_at')


class VendorCampaignHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignApproval
        fields = ('decision', 'feedback', 'created_at')


class CampaignDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=(
        'approve', 'reject', 'changes_requested', 'activate',
        'resume', 'confirm_cancellation', 'deny_cancellation',
    ))
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    approved_budget_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal('0'),
    )


class CampaignEventInputSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=('click',))


class AdminVendorDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=('approved', 'rejected', 'suspended', 'reactivated'))
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=5000)


class AdminVendorVerificationDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=('approved', 'rejected'))
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=5000)
