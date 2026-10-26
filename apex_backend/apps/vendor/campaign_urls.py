from django.urls import path

from .campaign_views import (
    ActiveCampaignListView,
    CampaignClickEventView,
    VendorCampaignActionView,
    VendorCampaignAssetView,
    VendorCampaignDetailView,
    VendorCampaignListCreateView,
    VendorCampaignReportCsvView,
    VendorCampaignReportView,
    VendorCampaignSubmitView,
)

urlpatterns = [
    path('active/', ActiveCampaignListView.as_view(), name='active-campaign-list'),
    path('', VendorCampaignListCreateView.as_view(), name='vendor-campaign-list'),
    path('<uuid:campaign_id>/', VendorCampaignDetailView.as_view(), name='vendor-campaign-detail'),
    path('<uuid:campaign_id>/submit/', VendorCampaignSubmitView.as_view(), name='vendor-campaign-submit'),
    path('<uuid:campaign_id>/actions/', VendorCampaignActionView.as_view(), name='vendor-campaign-action'),
    path('<uuid:campaign_id>/assets/', VendorCampaignAssetView.as_view(), name='vendor-campaign-assets'),
    path('<uuid:campaign_id>/events/', CampaignClickEventView.as_view(), name='campaign-event'),
    path('<uuid:campaign_id>/report/', VendorCampaignReportView.as_view(), name='vendor-campaign-report'),
    path('<uuid:campaign_id>/report.csv', VendorCampaignReportCsvView.as_view(), name='vendor-campaign-report-csv'),
]
