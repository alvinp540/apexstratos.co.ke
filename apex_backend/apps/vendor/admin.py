from django.contrib import admin
from .models import (
    CampaignApproval,
    CampaignAsset,
    CampaignEvent,
    SponsorshipCampaign,
    VendorJob,
    VendorProfile,
    VendorRating,
    VendorVerification,
)

@admin.register(VendorJob)
class VendorJobAdmin(admin.ModelAdmin):
    list_display = ('title', 'vendor', 'profession_required', 'status', 'priority', 'created_at')
    list_filter = ('status', 'priority')

admin.site.register(VendorRating)


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'category', 'status', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('business_name', 'user__email', 'contact_email')
    readonly_fields = ('id', 'user', 'status', 'admin_feedback', 'created_at', 'updated_at', 'reviewed_by', 'reviewed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VendorVerification)
class VendorVerificationAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'document_type', 'status', 'created_at', 'reviewed_at')
    list_filter = ('status', 'document_type')
    readonly_fields = ('id', 'vendor', 'document', 'status', 'admin_feedback', 'created_at', 'reviewed_by', 'reviewed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SponsorshipCampaign)
class SponsorshipCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'campaign_type', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'campaign_type', 'study_area')
    search_fields = ('name', 'vendor__business_name', 'description')
    readonly_fields = tuple(field.name for field in SponsorshipCampaign._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CampaignAsset)
class CampaignAssetAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'description', 'uploaded_by', 'created_at')
    readonly_fields = tuple(field.name for field in CampaignAsset._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CampaignApproval)
class CampaignApprovalAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'decision', 'actor', 'created_at')
    readonly_fields = tuple(field.name for field in CampaignApproval._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CampaignEvent)
class CampaignEventAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'event_type', 'user', 'source', 'occurred_at')
    list_filter = ('event_type', 'source', 'occurred_at')
    readonly_fields = tuple(field.name for field in CampaignEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
