from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from apps.accounts.models import User
from .models import FraudLog, AuditLog


class FraudLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FraudLog
        fields = (
            'id', 'user', 'event_type', 'severity', 'description',
            'ip_address', 'metadata', 'is_resolved', 'created_at',
        )
        read_only_fields = fields


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = (
            'id', 'user', 'action', 'model_name',
            'object_id', 'changes', 'ip_address', 'created_at',
        )
        read_only_fields = fields


class AdminAccountCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('A user with this username already exists.')
        return value


class AdminAccountRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=('professional', 'vendor', 'admin'))
