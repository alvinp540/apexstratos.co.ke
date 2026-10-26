from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin


class IsVendor(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'vendor'


class IsApprovedVendor(BasePermission):
    message = 'An approved vendor profile is required for this action.'

    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated
            and user.role == 'vendor'
            and getattr(getattr(user, 'vendor_profile', None), 'status', None) == 'approved'
        )


class IsProfessional(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'professional'


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return request.user.is_authenticated
        return request.user.is_authenticated and request.user.is_admin
