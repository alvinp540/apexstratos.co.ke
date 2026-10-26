from django.urls import path

from .campaign_views import (
    VendorCampaignDashboardView,
    VendorOnboardingView,
    VendorVerificationListCreateView,
)

urlpatterns = [
    path('onboarding/', VendorOnboardingView.as_view(), name='vendor-onboarding'),
    path('profile/', VendorOnboardingView.as_view(), name='vendor-profile'),
    path('verifications/', VendorVerificationListCreateView.as_view(), name='vendor-verifications'),
    path('dashboard/', VendorCampaignDashboardView.as_view(), name='vendor-campaign-dashboard'),
]
