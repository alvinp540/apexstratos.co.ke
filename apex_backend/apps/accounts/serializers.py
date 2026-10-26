from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User, Subscription


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('email', 'username', 'password', 'password2', 'role', 'phone_number')

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        if attrs.get('role') == 'admin':
            raise serializers.ValidationError({'role': 'Administrator accounts cannot be created through registration.'})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        Subscription.objects.create(user=user, plan='free')
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'role', 'is_email_verified',
                  'phone_number', 'created_at', 'is_admin', 'is_active', 'is_superuser')
        read_only_fields = ('id', 'is_email_verified', 'created_at', 'is_active', 'is_superuser')

    def get_is_admin(self, user):
        return user.is_admin


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ('id', 'plan', 'status', 'start_date', 'end_date', 'auto_renew')
        read_only_fields = ('id', 'start_date')


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
