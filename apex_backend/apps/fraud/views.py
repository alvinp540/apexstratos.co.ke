from django.db import transaction
from django.db import IntegrityError
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import FraudLog, AuditLog
from .serializers import (
    AdminAccountCreateSerializer,
    AdminAccountRoleSerializer,
    FraudLogSerializer,
    AuditLogSerializer,
)
from apps.accounts.permissions import IsAdmin
from apps.accounts.serializers import UserSerializer
from apps.accounts.models import Subscription, User
from utils.pagination import StandardResultsPagination


class AdminAccountCreateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = AdminAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    **serializer.validated_data,
                    role='admin',
                    is_staff=True,
                    is_email_verified=True,
                )
                Subscription.objects.create(user=user, plan='free')
                AuditLog.objects.create(
                    user=request.user,
                    action='admin_account_created',
                    model_name='User',
                    object_id=str(user.id),
                    changes={'role': {'from': None, 'to': 'admin'}},
                    ip_address=request.META.get('REMOTE_ADDR'),
                )
        except IntegrityError:
            return Response(
                {'detail': 'An account with this email or username already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        users = User.objects.all().order_by('-created_at')
        search = request.query_params.get('search', '').strip()
        if len(search) > 120:
            return Response(
                {'search': 'Search must be 120 characters or fewer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if search:
            users = users.filter(Q(email__icontains=search) | Q(username__icontains=search))
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(users, request)
        return paginator.get_paginated_response(UserSerializer(page, many=True).data)


class AdminUserStatusView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        is_active = request.data.get('is_active')
        if is_active is not None:
            user.is_active = is_active
            user.save(update_fields=['is_active'])
        return Response(UserSerializer(user).data)


class AdminUserRoleView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, user_id):
        serializer = AdminAccountRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data['role']

        with transaction.atomic():
            list(
                User.objects.select_for_update()
                .filter(is_active=True)
                .filter(Q(role='admin') | Q(is_staff=True) | Q(is_superuser=True))
                .order_by('pk')
                .values_list('pk', flat=True)
            )
            user = get_object_or_404(User.objects.select_for_update(), id=user_id)
            if user.pk == request.user.pk:
                return Response(
                    {'detail': 'You cannot change your own account type.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user.is_superuser and new_role != 'admin':
                return Response(
                    {'detail': 'Superuser account types cannot be changed here.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            previous_role = user.role
            if previous_role == new_role:
                return Response(UserSerializer(user).data)

            if previous_role == 'admin' and new_role != 'admin' and not user.is_superuser:
                other_active_admins = User.objects.filter(is_active=True).filter(
                    Q(role='admin') | Q(is_staff=True) | Q(is_superuser=True)
                ).exclude(pk=user.pk).count()
                if not other_active_admins:
                    return Response(
                        {'detail': 'Promote another active administrator before removing the last admin role.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            user.role = new_role
            if not user.is_superuser:
                user.is_staff = new_role == 'admin'
            user.save(update_fields=('role', 'is_staff'))
            AuditLog.objects.create(
                user=request.user,
                action='user_role_changed',
                model_name='User',
                object_id=str(user.id),
                changes={'role': {'from': previous_role, 'to': new_role}},
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        return Response(UserSerializer(user).data)


class FraudLogListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        logs = FraudLog.objects.order_by('-created_at')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(logs, request)
        return paginator.get_paginated_response(FraudLogSerializer(page, many=True).data)


class FraudLogResolveView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, log_id):
        log = get_object_or_404(FraudLog, id=log_id)
        log.is_resolved = True
        log.save(update_fields=['is_resolved'])
        return Response({'status': 'resolved'})


class AuditLogListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        logs = AuditLog.objects.order_by('-created_at')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(logs, request)
        return paginator.get_paginated_response(AuditLogSerializer(page, many=True).data)


class AdminEscrowListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        from apps.escrow.models import EscrowPayment
        from apps.escrow.serializers import EscrowPaymentSerializer
        escrows = EscrowPayment.objects.all().order_by('-created_at')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(escrows, request)
        return paginator.get_paginated_response(EscrowPaymentSerializer(page, many=True).data)


class AdminRecalculateRankingsView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        from apps.rankings.tasks import recalculate_all_rankings
        recalculate_all_rankings.delay()
        return Response({'message': 'Global ranking recalculation started.'})
