from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Subscription


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'username', 'role', 'is_email_verified', 'is_active', 'created_at')
    list_filter = ('role', 'is_email_verified', 'is_active')
    search_fields = ('email', 'username')
    ordering = ('-created_at',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('APEX', {'fields': ('role', 'is_email_verified', 'phone_number')}),
    )

    def save_model(self, request, obj, form, change):
        if obj.role == 'admin':
            obj.is_staff = True
        super().save_model(request, obj, form, change)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'start_date', 'end_date')
    list_filter = ('plan', 'status')
