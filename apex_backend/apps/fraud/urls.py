from django.urls import path
from .views import (
    AdminAccountCreateView, AdminUserListView, AdminUserRoleView, AdminUserStatusView,
    FraudLogListView, FraudLogResolveView,
    AuditLogListView, AdminEscrowListView, AdminRecalculateRankingsView,
)

urlpatterns = [
    path('users/admin-accounts/', AdminAccountCreateView.as_view(), name='admin-account-create'),
    path('users/', AdminUserListView.as_view(), name='admin-user-list'),
    path('users/<uuid:user_id>/role/', AdminUserRoleView.as_view(), name='admin-user-role'),
    path('users/<uuid:user_id>/status/', AdminUserStatusView.as_view()),
    path('fraud-logs/', FraudLogListView.as_view()),
    path('fraud-logs/<uuid:log_id>/resolve/', FraudLogResolveView.as_view()),
    path('audit-logs/', AuditLogListView.as_view()),
    path('escrow/', AdminEscrowListView.as_view()),
    path('rankings/recalculate/', AdminRecalculateRankingsView.as_view()),
]
