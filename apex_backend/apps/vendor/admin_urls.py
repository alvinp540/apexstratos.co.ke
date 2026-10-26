from django.urls import path

from .campaign_views import (
    AdminCampaignDecisionView,
    AdminCampaignListView,
    AdminVendorDecisionView,
    AdminVendorListView,
    AdminVendorVerificationDecisionView,
    AdminVendorVerificationDocumentView,
)

urlpatterns = [
    path('', AdminVendorListView.as_view(), name='admin-vendor-list'),
    path('<uuid:vendor_id>/decision/', AdminVendorDecisionView.as_view(), name='admin-vendor-decision'),
    path('verifications/<uuid:verification_id>/decision/', AdminVendorVerificationDecisionView.as_view(), name='admin-vendor-verification-decision'),
    path('verifications/<uuid:verification_id>/document/', AdminVendorVerificationDocumentView.as_view(), name='admin-vendor-verification-document'),
    path('campaigns/', AdminCampaignListView.as_view(), name='admin-campaign-list'),
    path('campaigns/<uuid:campaign_id>/decision/', AdminCampaignDecisionView.as_view(), name='admin-campaign-decision'),
]
