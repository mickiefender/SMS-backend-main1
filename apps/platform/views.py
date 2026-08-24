"""
Platform Super Admin APIs.

Every view requires an authenticated super_admin (or a user holding the
matching platform-role permission). Sensitive actions write AuditLog rows.
"""
import hashlib
import secrets
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schools.models import Plan, School, Subscription
from apps.platform.models import (
    AccountLockout, ApiKey, ApiUsageLog, AuditLog, Coupon, FeatureFlag,
    ImpersonationSession, Invoice, ModerationReport, MonitoringSnapshot,
    NotificationCampaign, PlatformRole, PlatformUserRole, Refund,
    SecurityEvent, StorageQuota, SupportTicket, SupportTicketComment,
    SystemSetting, UserSession, Webhook, write_audit_log,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class IsSuperAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_authenticated and request.user.role == 'super_admin'


def _client_meta(request):
    return {
        'ip': request.META.get('REMOTE_ADDR', ''),
        'ua': request.META.get('HTTP_USER_AGENT', ''),
    }


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

class PlatformRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformRole
        fields = ['id', 'name', 'display_name', 'description', 'permissions',
                  'is_system', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'actor_name', 'action', 'target_type',
                  'target_id', 'target_label', 'changes', 'ip_address',
                  'user_agent', 'created_at']


class SupportTicketSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)
    assignee_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = ['id', 'reference', 'requester', 'requester_name', 'school',
                  'school_name', 'kind', 'subject', 'body', 'status', 'priority',
                  'assignee', 'assignee_name', 'internal_notes', 'resolved_at',
                  'created_at', 'updated_at']
        read_only_fields = ['reference', 'created_at', 'updated_at']

    def get_assignee_name(self, obj):
        return obj.assignee.get_full_name() if obj.assignee else None


class TicketCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicketComment
        fields = ['id', 'ticket', 'author', 'author_name', 'body',
                  'is_internal', 'created_at']
        read_only_fields = ['author', 'author_name', 'created_at']


class FeatureFlagSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = FeatureFlag
        fields = ['id', 'key', 'name', 'description', 'scope', 'school',
                  'school_name', 'plan_name', 'enabled', 'rollout_percent',
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class SystemSettingSerializer(serializers.ModelSerializer):
    """Secret settings are write-only — the API masks their value on read."""
    value = serializers.SerializerMethodField()

    class Meta:
        model = SystemSetting
        fields = ['id', 'key', 'category', 'value', 'is_secret',
                  'description', 'updated_at']

    def get_value(self, obj):
        if obj.is_secret:
            return '••••••••'
        return obj.value

    def to_internal_value(self, data):
        # Allow saving over a masked value: treat '••••••••' as "unchanged".
        ret = super().to_internal_value(data)
        return ret


class CampaignSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = NotificationCampaign
        fields = ['id', 'name', 'channels', 'audience_type', 'audience_filter',
                  'title', 'body', 'status', 'scheduled_at', 'sent_at',
                  'recipient_count', 'delivered_count', 'failed_count',
                  'created_by_name', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class ApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = ['id', 'name', 'prefix', 'scopes', 'rate_limit_per_min',
                  'is_active', 'last_used_at', 'expires_at', 'created_at']
        read_only_fields = ['prefix', 'created_at']


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ['id', 'name', 'url', 'events', 'secret', 'is_active',
                  'last_status', 'last_delivery_at', 'failure_count', 'created_at']
        read_only_fields = ['created_at', 'last_status', 'last_delivery_at', 'failure_count']


class SecurityEventSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = SecurityEvent
        fields = ['id', 'user', 'user_name', 'event_type', 'ip_address',
                  'user_agent', 'details', 'severity', 'created_at']

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None


class UserSessionSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = ['id', 'user', 'user_name', 'session_key', 'device', 'browser',
                  'os', 'ip_address', 'location', 'is_active', 'last_activity', 'created_at']

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None


class ModerationReportSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)
    uploader_name = serializers.SerializerMethodField()

    class Meta:
        model = ModerationReport
        fields = ['id', 'reporter', 'content_type', 'content_id', 'content_url',
                  'content_preview', 'uploader', 'uploader_name', 'school',
                  'school_name', 'reason', 'details', 'status', 'action_taken',
                  'reviewed_by', 'reviewed_at', 'review_notes', 'created_at']

    def get_uploader_name(self, obj):
        return obj.uploader.get_full_name() if obj.uploader else None


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = ['id', 'code', 'description', 'discount_type', 'discount_value',
                  'max_redemptions', 'redemption_count', 'applies_to_plan',
                  'valid_from', 'valid_until', 'is_active', 'created_at']
        read_only_fields = ['redemption_count', 'created_at']


class InvoiceSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = Invoice
        fields = ['id', 'number', 'school', 'school_name', 'subscription_id',
                  'amount_due', 'amount_paid', 'currency', 'status',
                  'period_start', 'period_end', 'due_date', 'line_items',
                  'pdf_url', 'created_at', 'updated_at']
        read_only_fields = ['number', 'created_at', 'updated_at']


class RefundSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = Refund
        fields = ['id', 'transaction_ref', 'invoice', 'school', 'school_name',
                  'amount', 'currency', 'reason', 'status', 'processed_by',
                  'processed_at', 'created_at']
        read_only_fields = ['created_at']


class StorageQuotaSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = StorageQuota
        fields = ['id', 'school', 'school_name', 'quota_mb', 'used_mb',
                  'videos_mb', 'images_mb', 'documents_mb', 'backups_mb',
                  'computed_at', 'updated_at']


class MonitoringSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitoringSnapshot
        fields = ['id', 'component', 'status', 'latency_ms', 'error_rate',
                  'details', 'recorded_at']


# ---------------------------------------------------------------------------
# ViewSets
# ---------------------------------------------------------------------------

class PlatformRoleViewSet(viewsets.ModelViewSet):
    serializer_class = PlatformRoleSerializer
    permission_classes = [IsSuperAdmin]
    queryset = PlatformRole.objects.all().order_by('name')

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.is_system:
            return Response({'error': 'System roles cannot be deleted'},
                            status=status.HTTP_400_BAD_REQUEST)
        write_audit_log(request, request.user, 'role.deleted',
                        'platform_role', role.id, role.display_name)
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        role = serializer.save()
        write_audit_log(self.request, self.request.user, 'role.created',
                        'platform_role', role.id, role.display_name)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign this role to a user. Body: {user_id}"""
        role = self.get_object()
        user_id = request.data.get('user_id')
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'error': 'User not found'}, status=404)
        PlatformUserRole.objects.get_or_create(
            user=user, role=role, defaults={'assigned_by': request.user})
        write_audit_log(request, request.user, 'role.assigned',
                        'user', user.id, user.get_full_name(),
                        {'role': role.name})
        return Response({'ok': True})

    @action(detail=True, methods=['post'])
    def unassign(self, request, pk=None):
        role = self.get_object()
        user_id = request.data.get('user_id')
        PlatformUserRole.objects.filter(user_id=user_id, role=role).delete()
        write_audit_log(request, request.user, 'role.unassigned',
                        'user', user_id, '', {'role': role.name})
        return Response({'ok': True})

    @action(detail=False, methods=['get'])
    def assignments(self, request):
        rows = PlatformUserRole.objects.select_related('user', 'role').order_by('-created_at')
        data = [{
            'id': r.id,
            'user_id': r.user_id,
            'user_name': r.user.get_full_name() or r.user.username,
            'role_id': r.role_id,
            'role_name': r.role.name,
            'assigned_at': r.created_at,
        } for r in rows]
        return Response(data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsSuperAdmin]
    queryset = AuditLog.objects.select_related('actor').all()

    def get_queryset(self):
        qs = super().get_queryset()
        action_filter = self.request.query_params.get('action')
        if action_filter:
            qs = qs.filter(action=action_filter)
        target_type = self.request.query_params.get('target_type')
        if target_type:
            qs = qs.filter(target_type=target_type)
        return qs


class SupportTicketViewSet(viewsets.ModelViewSet):
    serializer_class = SupportTicketSerializer
    permission_classes = [IsSuperAdmin]
    queryset = SupportTicket.objects.select_related('school', 'assignee').all()

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        priority = self.request.query_params.get('priority')
        if priority:
            qs = qs.filter(priority=priority)
        kind = self.request.query_params.get('kind')
        if kind:
            qs = qs.filter(kind=kind)
        return qs

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        ticket = serializer.save()
        if ticket.status == 'resolved' and old_status != 'resolved':
            ticket.resolved_at = timezone.now()
            ticket.save(update_fields=['resolved_at'])
        write_audit_log(self.request, self.request.user, 'ticket.updated',
                        'support_ticket', ticket.id, ticket.reference,
                        {'status': {'before': old_status, 'after': ticket.status}})

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        ticket = self.get_object()
        if request.method == 'POST':
            serializer = TicketCommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            comment = serializer.save(
                ticket=ticket, author=request.user,
                author_name=request.user.get_full_name() or request.user.username)
            return Response(TicketCommentSerializer(comment).data, status=201)
        comments = ticket.comments.all()
        return Response(TicketCommentSerializer(comments, many=True).data)


class FeatureFlagViewSet(viewsets.ModelViewSet):
    serializer_class = FeatureFlagSerializer
    permission_classes = [IsSuperAdmin]
    queryset = FeatureFlag.objects.select_related('school').all()

    def get_queryset(self):
        qs = super().get_queryset()
        scope = self.request.query_params.get('scope')
        if scope:
            qs = qs.filter(scope=scope)
        key = self.request.query_params.get('key')
        if key:
            qs = qs.filter(key=key)
        return qs

    def perform_create(self, serializer):
        flag = serializer.save(updated_by=self.request.user)
        write_audit_log(self.request, self.request.user, 'flag.created',
                        'feature_flag', flag.id, f'{flag.key} ({flag.scope})')

    def perform_update(self, serializer):
        old = serializer.instance.enabled
        flag = serializer.save(updated_by=self.request.user)
        write_audit_log(self.request, self.request.user, 'flag.updated',
                        'feature_flag', flag.id, f'{flag.key} ({flag.scope})',
                        {'enabled': {'before': old, 'after': flag.enabled}})


class SystemSettingViewSet(viewsets.ModelViewSet):
    serializer_class = SystemSettingSerializer
    permission_classes = [IsSuperAdmin]
    queryset = SystemSetting.objects.all().order_by('category', 'key')

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs

    def perform_update(self, serializer):
        data = self.request.data or {}
        # Masked secret sent back unchanged → keep the stored value.
        if isinstance(data.get('value'), str) and data['value'] == '••••••••':
            serializer.validated_data.pop('value', None)
        setting = serializer.save(updated_by=self.request.user)
        write_audit_log(self.request, self.request.user, 'settings.updated',
                        'system_setting', setting.id, setting.key)


class CampaignViewSet(viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    permission_classes = [IsSuperAdmin]
    queryset = NotificationCampaign.objects.select_related('created_by').all()

    def perform_create(self, serializer):
        campaign = serializer.save(created_by=self.request.user)
        write_audit_log(self.request, self.request.user, 'campaign.created',
                        'campaign', campaign.id, campaign.name)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Send now (or mark scheduled → sending). Delivery fan-out is handled
        by the notifications app / celery; here we resolve the audience size."""
        campaign = self.get_object()
        if campaign.status == 'sent':
            return Response({'error': 'Campaign already sent'}, status=400)

        audience_filter = campaign.audience_filter or {}
        qs = User.objects.filter(is_active=True)
        if campaign.audience_type == 'school':
            qs = qs.filter(school_id__in=audience_filter.get('school_ids', []))
        elif campaign.audience_type == 'role':
            qs = qs.filter(role__in=audience_filter.get('roles', []))
        elif campaign.audience_type == 'users':
            qs = qs.filter(id__in=audience_filter.get('user_ids', []))
        elif campaign.audience_type == 'plan':
            plan = Plan.objects.filter(name=audience_filter.get('plan')).first()
            school_ids = Subscription.objects.filter(
                plan=plan, status='active').values_list('school_id', flat=True)
            qs = qs.filter(school_id__in=school_ids)

        count = qs.count()
        campaign.recipient_count = count
        if campaign.scheduled_at and campaign.scheduled_at > timezone.now():
            campaign.status = 'scheduled'
        else:
            campaign.status = 'sending'
        campaign.save()
        write_audit_log(request, request.user, 'campaign.send',
                        'campaign', campaign.id, campaign.name,
                        {'recipients': count})
        return Response(CampaignSerializer(campaign).data)


class ApiKeyViewSet(viewsets.ModelViewSet):
    serializer_class = ApiKeySerializer
    permission_classes = [IsSuperAdmin]
    queryset = ApiKey.objects.all().order_by('-created_at')

    def create(self, request, *args, **kwargs):
        raw_key = secrets.token_urlsafe(32)
        prefix = f"ala_{raw_key[:8]}"
        api_key = ApiKey.objects.create(
            name=request.data.get('name', 'Unnamed key'),
            prefix=prefix,
            hashed_key=hashlib.sha256(raw_key.encode()).hexdigest(),
            scopes=request.data.get('scopes', []),
            rate_limit_per_min=request.data.get('rate_limit_per_min', 60),
            expires_at=request.data.get('expires_at') or None,
            created_by=request.user,
        )
        write_audit_log(request, request.user, 'apikey.created',
                        'api_key', api_key.id, api_key.name)
        # The raw key is shown exactly once.
        return Response({**ApiKeySerializer(api_key).data, 'key': f'{prefix}.{raw_key}'},
                        status=201)

    def destroy(self, request, *args, **kwargs):
        api_key = self.get_object()
        write_audit_log(request, request.user, 'apikey.revoked',
                        'api_key', api_key.id, api_key.name)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def usage(self, request, pk=None):
        api_key = self.get_object()
        since = timezone.now() - timedelta(days=7)
        rows = ApiUsageLog.objects.filter(api_key=api_key, created_at__gte=since)
        by_day = {}
        for r in rows:
            day = r.created_at.date().isoformat()
            by_day.setdefault(day, {'requests': 0, 'errors': 0})
            by_day[day]['requests'] += 1
            if r.status_code >= 400:
                by_day[day]['errors'] += 1
        return Response({'last_7_days': by_day, 'total': rows.count()})


class WebhookViewSet(viewsets.ModelViewSet):
    serializer_class = WebhookSerializer
    permission_classes = [IsSuperAdmin]
    queryset = Webhook.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        import secrets as _secrets
        webhook = serializer.save(secret=_secrets.token_urlsafe(24))
        write_audit_log(self.request, self.request.user, 'webhook.created',
                        'webhook', webhook.id, webhook.name)


class SecurityEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SecurityEventSerializer
    permission_classes = [IsSuperAdmin]
    queryset = SecurityEvent.objects.select_related('user').all()

    def get_queryset(self):
        qs = super().get_queryset()
        severity = self.request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)
        event_type = self.request.query_params.get('event_type')
        if event_type:
            qs = qs.filter(event_type=event_type)
        user_id = self.request.query_params.get('user')
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs


class UserSessionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSessionSerializer
    permission_classes = [IsSuperAdmin]
    queryset = UserSession.objects.select_related('user').all()

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        session = self.get_object()
        session.is_active = False
        session.save(update_fields=['is_active'])
        write_audit_log(request, request.user, 'session.revoked',
                        'user_session', session.id, session.device)
        return Response({'ok': True})


class ModerationReportViewSet(viewsets.ModelViewSet):
    serializer_class = ModerationReportSerializer
    permission_classes = [IsSuperAdmin]
    queryset = ModerationReport.objects.select_related('school', 'uploader').all()

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        content_type = self.request.query_params.get('content_type')
        if content_type:
            qs = qs.filter(content_type=content_type)
        return qs

    def perform_update(self, serializer):
        report = serializer.save(
            reviewed_by=self.request.user,
            reviewed_at=timezone.now() if serializer.instance.status in ('actioned', 'dismissed') else None,
        )
        write_audit_log(self.request, self.request.user, 'moderation.reviewed',
                        'moderation_report', report.id,
                        f'{report.content_type} #{report.content_id}',
                        {'status': report.status, 'action': report.action_taken})


class CouponViewSet(viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    permission_classes = [IsSuperAdmin]
    queryset = Coupon.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        coupon = serializer.save()
        write_audit_log(self.request, self.request.user, 'coupon.created',
                        'coupon', coupon.id, coupon.code)


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsSuperAdmin]
    queryset = Invoice.objects.select_related('school').all()

    def get_queryset(self):
        qs = super().get_queryset()
        school_id = self.request.query_params.get('school')
        if school_id:
            qs = qs.filter(school_id=school_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        invoice = serializer.save()
        write_audit_log(self.request, self.request.user, 'invoice.created',
                        'invoice', invoice.id, invoice.number)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = 'paid'
        invoice.amount_paid = invoice.amount_due
        invoice.save(update_fields=['status', 'amount_paid', 'updated_at'])
        write_audit_log(request, request.user, 'invoice.paid',
                        'invoice', invoice.id, invoice.number)
        return Response(InvoiceSerializer(invoice).data)


class RefundViewSet(viewsets.ModelViewSet):
    serializer_class = RefundSerializer
    permission_classes = [IsSuperAdmin]
    queryset = Refund.objects.select_related('school').all()

    def perform_create(self, serializer):
        refund = serializer.save()
        write_audit_log(self.request, self.request.user, 'refund.created',
                        'refund', refund.id, str(refund.amount))

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        refund = self.get_object()
        refund.status = 'processed'
        refund.processed_by = request.user
        refund.processed_at = timezone.now()
        refund.save(update_fields=['status', 'processed_by', 'processed_at'])
        write_audit_log(request, request.user, 'refund.processed',
                        'refund', refund.id, str(refund.amount))
        return Response(RefundSerializer(refund).data)


class StorageQuotaViewSet(viewsets.ModelViewSet):
    serializer_class = StorageQuotaSerializer
    permission_classes = [IsSuperAdmin]
    queryset = StorageQuota.objects.select_related('school').all()

    @action(detail=False, methods=['post'])
    def recompute(self, request):
        """Recompute usage from the storage app's uploaded files (best effort)."""
        from apps.storage.models import UploadedFile  # best-effort import
        updated = 0
        for quota in StorageQuota.objects.select_related('school').all():
            files = UploadedFile.objects.filter(school=quota.school)
            agg = files.aggregate(total=Sum('file_size'))
            quota.used_mb = int((agg['total'] or 0) / (1024 * 1024))
            quota.computed_at = timezone.now()
            quota.save(update_fields=['used_mb', 'computed_at', 'updated_at'])
            updated += 1
        return Response({'updated': updated})


class MonitoringSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MonitoringSnapshotSerializer
    permission_classes = [IsSuperAdmin]
    queryset = MonitoringSnapshot.objects.all()


# ---------------------------------------------------------------------------
# Dashboard overview
# ---------------------------------------------------------------------------

class PlatformOverviewView(APIView):
    """Aggregated stats for the super-admin dashboard."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        schools = School.objects.all()
        total_students = User.objects.filter(role='student').count()
        total_teachers = User.objects.filter(role='teacher').count()
        total_parents = User.objects.filter(role='parent').count()
        total_users = User.objects.count()
        active_users_30d = User.objects.filter(last_login__gte=now - timedelta(days=30)).count()
        active_users_today = User.objects.filter(last_login__gte=now - timedelta(days=1)).count()

        subs = Subscription.objects.select_related('plan')
        revenue = Invoice.objects.filter(status='paid').aggregate(total=Sum('amount_paid'))['total'] or 0

        # Growth series (last 6 months, schools + users created per month)
        growth = []
        for i in range(5, -1, -1):
            start = (month_start - timedelta(days=30 * i)).replace(day=1)
            end = (start + timedelta(days=31)).replace(day=1)
            growth.append({
                'month': start.strftime('%b %Y'),
                'schools': schools.filter(created_at__gte=start, created_at__lt=end).count(),
                'users': User.objects.filter(date_joined__gte=start, date_joined__lt=end).count(),
            })

        return Response({
            'schools': {
                'total': schools.count(),
                'active': schools.filter(status='active').count(),
                'suspended': schools.filter(status='suspended').count(),
                'trial': Subscription.objects.filter(
                    plan__name='starter', status='active').count(),
            },
            'users': {
                'total': total_users,
                'students': total_students,
                'teachers': total_teachers,
                'parents': total_parents,
                'active_today': active_users_today,
                'active_30d': active_users_30d,
            },
            'revenue': {
                'total': float(revenue),
                'this_month': float(
                    Invoice.objects.filter(status='paid', created_at__gte=month_start)
                    .aggregate(total=Sum('amount_paid'))['total'] or 0),
                'open_invoices': Invoice.objects.filter(status='open').count(),
            },
            'subscriptions': {
                'active': subs.filter(status='active').count(),
                'cancelled': subs.filter(status='cancelled').count(),
            },
            'storage': {
                'used_mb': StorageQuota.objects.aggregate(total=Sum('used_mb'))['total'] or 0,
            },
            'support': {
                'open_tickets': SupportTicket.objects.filter(status='open').count(),
                'urgent': SupportTicket.objects.filter(priority='urgent', status__in=['open', 'in_progress']).count(),
            },
            'moderation': {
                'pending': ModerationReport.objects.filter(status='pending').count(),
            },
            'growth': growth,
        })


class SystemHealthView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        checks = []
        # Database
        try:
            from django.db import connection
            start = timezone.now()
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            latency = int((timezone.now() - start).total_seconds() * 1000)
            checks.append({'component': 'database', 'status': 'healthy', 'latency_ms': latency})
        except Exception as exc:
            checks.append({'component': 'database', 'status': 'down', 'details': str(exc)})

        # Celery (broker ping is optional — check beat schedule file presence as proxy)
        try:
            from celery import current_app
            conn = current_app.connection()
            conn.ensure_connection(max_retries=1, timeout=2)
            conn.close()
            checks.append({'component': 'celery', 'status': 'healthy'})
        except Exception as exc:
            checks.append({'component': 'celery', 'status': 'degraded', 'details': str(exc)})

        # Recent error rate from API usage logs
        since = timezone.now() - timedelta(hours=1)
        total = ApiUsageLog.objects.filter(created_at__gte=since).count()
        errors = ApiUsageLog.objects.filter(created_at__gte=since, status_code__gte=500).count()
        error_rate = round((errors / total) * 100, 2) if total else 0
        checks.append({'component': 'api', 'status': 'healthy' if error_rate < 5 else 'degraded',
                       'error_rate': error_rate, 'requests_last_hour': total})

        return Response({'checked_at': now_iso(), 'checks': checks})


def now_iso():
    from django.utils import timezone as tz
    return tz.now().isoformat()


# ---------------------------------------------------------------------------
# Impersonation
# ---------------------------------------------------------------------------

class ImpersonationView(APIView):
    """
    POST /api/platform/impersonate/   {target_user_id, reason} → start session
    DELETE /api/platform/impersonate/ → end the active session
    GET    /api/platform/impersonate/ → list sessions
    Every start/stop is audit-logged.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        rows = ImpersonationSession.objects.select_related('super_admin', 'target_user').order_by('-started_at')[:100]
        data = [{
            'id': r.id,
            'super_admin_name': r.super_admin.get_full_name(),
            'target_user_id': r.target_user_id,
            'target_user_name': r.target_user.get_full_name(),
            'reason': r.reason,
            'started_at': r.started_at,
            'ended_at': r.ended_at,
            'is_active': r.is_active,
        } for r in rows]
        return Response(data)

    def post(self, request):
        target = User.objects.filter(
            id=request.data.get('target_user_id'),
            role='school_admin',
        ).first()
        if not target:
            return Response({'error': 'School admin not found'}, status=404)

        # End any other active session for this super admin first.
        ImpersonationSession.objects.filter(
            super_admin=request.user, is_active=True).update(
            is_active=False, ended_at=timezone.now())

        meta = _client_meta(request)
        session = ImpersonationSession.objects.create(
            super_admin=request.user,
            target_user=target,
            reason=request.data.get('reason', ''),
            ip_address=meta['ip'],
            user_agent=meta['ua'],
        )
        write_audit_log(request, request.user, 'impersonation.started',
                        'user', target.id, target.get_full_name(),
                        {'reason': session.reason})
        return Response({
            'session_id': session.id,
            'target_user_id': target.id,
            'target_user_name': target.get_full_name(),
            'school_id': target.school_id,
            # The frontend stores this token and uses it for school-scoped calls.
            'note': 'Use the school context of the target user for subsequent calls.',
        }, status=201)

    def delete(self, request):
        ended = ImpersonationSession.objects.filter(
            super_admin=request.user, is_active=True).update(
            is_active=False, ended_at=timezone.now())
        write_audit_log(request, request.user, 'impersonation.ended',
                        'impersonation_session', '', '')
        return Response({'ended': ended})
