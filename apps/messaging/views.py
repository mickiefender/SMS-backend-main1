from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.db.models import Sum, Count
from django.shortcuts import get_object_or_404
from django.conf import settings
import hashlib
import hmac
import os
import re
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model
from core.permissions import (
    IsSchoolAdminOrHigher, IsTeacher, IsStudent,
    CanManageNotices, CanSendMessages, CanViewRecipients,
)
from .models import (
    Message, Announcement, AnnouncementRead, Notice, PersonalNotice,
    SMSConfiguration, SMSBalance, SMSTemplate, SMSMessage, SMSJob, SMSCreditLedger,
)
from .serializers import (
    SMSConfigurationSerializer, SMSBalanceSerializer, SMSTemplateSerializer,
    SMSMessageSerializer, SMSJobSerializer,
)
from .services.sms import send_sms, render_message
from .serializers import MessageSerializer, AnnouncementSerializer, AnnouncementReadSerializer, NoticeSerializer, PersonalNoticeSerializer
from .tasks import (
    send_notice_email, send_announcement_email, send_personal_notice_email,
    send_notice_push, send_announcement_push, send_personal_notice_push,
)
from apps.schools.models import School

User = get_user_model()


def _is_sms_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.role in {"super_admin", "school_admin"}:
        return True
    if user.role == "teacher":
        return True
    try:
        return user.role_permission.has_permission("send_messages")
    except Exception:
        return False


def _school_for_request(request):
    if request.user.role == "super_admin":
        school_id = request.query_params.get("school_id") or request.data.get("school_id")
        if school_id:
            return get_object_or_404(School, pk=school_id)
    return request.user.school


def _audit(request, action, target, changes=None):
    try:
        from apps.platform.models import write_audit_log
        write_audit_log(request, request.user, action, "sms", target.pk, str(target), changes)
    except Exception:
        pass


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if self.action == 'list':
            # Show received messages by default
            return Message.objects.filter(recipient=user).order_by('-created_at')
        return Message.objects.filter(Q(sender=user) | Q(recipient=user))

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    @action(detail=False, methods=['get'])
    def sent(self, request):
        """Get sent messages"""
        messages = Message.objects.filter(sender=request.user).order_by('-created_at')
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a message as read"""
        message = self.get_object()
        if message.recipient == request.user:
            message.is_read = True
            message.save()
            return Response({'status': 'marked as read'})
        return Response({'error': 'Unauthorized'}, status=403)


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'super_admin':
            return Announcement.objects.all()
        
        # School admins see all announcements in their school
        if user.role == 'school_admin':
            return Announcement.objects.filter(school=user.school)
        
        # Teachers and students see published announcements in their school
        return Announcement.objects.filter(
            school=user.school,
            status='published'
        )

    def perform_create(self, serializer):
        """Create announcement and send emails when published"""
        print(f"[v0] Creating announcement. User ID: {self.request.user.pk}, Exists: {User.objects.filter(pk=self.request.user.pk).exists()}")
        
        # Always save without created_by first to avoid FK constraint issues
        # created_by is read_only in serializer anyway
        announcement = serializer.save(school=self.request.user.school)
        
        # Try to set created_by if user exists in DB
        try:
            if User.objects.filter(pk=self.request.user.pk).exists():
                announcement.created_by = self.request.user
                announcement.save(update_fields=['created_by'])
                print(f"[v0] Set created_by to user {self.request.user.pk}")
            else:
                print(f"[v0] User {self.request.user.pk} does not exist in database, created_by will be NULL")
        except Exception as e:
            print(f"[v0] Error setting created_by: {e}")
        
        # Auto-publish on create (align with Notice)
        announcement.status = 'published'
        announcement.published_date = timezone.now()
        announcement.save(update_fields=['status', 'published_date'])

        # Queue email + in-app/FCM push delivery to the resolved recipients
        # (audience flags + individually targeted recipients).
        send_announcement_email.delay(announcement.id)
        send_announcement_push.delay(announcement.id)
        print(f"[v0] Auto-published announcement {announcement.id}; email + push queued")

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanSendMessages()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish an announcement and send emails + push"""
        announcement = self.get_object()
        announcement.status = 'published'
        announcement.published_date = timezone.now()
        announcement.save()

        # Send emails + push asynchronously
        send_announcement_email.delay(announcement.id)
        send_announcement_push.delay(announcement.id)

        return Response({'status': 'announcement published; emails and push notifications queued'})

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark announcement as read by current user"""
        announcement = self.get_object()
        AnnouncementRead.objects.get_or_create(announcement=announcement, user=request.user)
        return Response({'status': 'marked as read'})

    @action(detail=True, methods=['get'])
    def read_by(self, request, pk=None):
        """Get list of users who read this announcement"""
        announcement = self.get_object()
        reads = AnnouncementRead.objects.filter(announcement=announcement)
        serializer = AnnouncementReadSerializer(reads, many=True)
        return Response(serializer.data)


class NoticeViewSet(viewsets.ModelViewSet):
    serializer_class = NoticeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'super_admin':
            return Notice.objects.all()
        
        # School admins see all notices in their school
        if user.role == 'school_admin':
            return Notice.objects.filter(school=user.school).order_by('-is_pinned', '-created_at')
        
        # Teachers and students see active notices in their school
        now = timezone.now()
        return Notice.objects.filter(
            school=user.school,
            expiry_date__isnull=True
        ) | Notice.objects.filter(
            school=user.school,
            expiry_date__gt=now
        )

    def perform_create(self, serializer):
        """Create notice and send emails asynchronously"""
        print(f"[v0] Creating notice. User ID: {self.request.user.pk}, Exists: {User.objects.filter(pk=self.request.user.pk).exists()}")
        
        # Always save without created_by first to avoid FK constraint issues
        # created_by is read_only in serializer anyway
        notice = serializer.save(school=self.request.user.school)
        
        # Try to set created_by if user exists in DB
        try:
            if User.objects.filter(pk=self.request.user.pk).exists():
                notice.created_by = self.request.user
                notice.save(update_fields=['created_by'])
                print(f"[v0] Set created_by to user {self.request.user.pk}")
            else:
                print(f"[v0] User {self.request.user.pk} does not exist in database, created_by will be NULL")
        except Exception as e:
            print(f"[v0] Error setting created_by: {e}")
        
        # Send emails + in-app/FCM push asynchronously
        send_notice_email.delay(notice.id)
        send_notice_push.delay(notice.id)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageNotices()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'], permission_classes=[CanViewRecipients])
    def recipients(self, request):
        """
        Directory of possible individual recipients (students + teachers)
        in the admin's school — powers the recipient picker on the
        Notices / Announcements pages.
        """
        school = request.user.school
        users = User.objects.filter(school=school, is_active=True, role__in=['student', 'teacher'])

        role_filter = request.query_params.get('role')
        if role_filter:
            users = users.filter(role=role_filter)

        search = request.query_params.get('search')
        if search:
            from django.db.models import Q as _Q
            users = users.filter(
                _Q(first_name__icontains=search) |
                _Q(last_name__icontains=search) |
                _Q(username__icontains=search) |
                _Q(email__icontains=search)
            )

        data = [
            {
                'id': u.id,
                'name': u.get_full_name() or u.username,
                'email': u.email,
                'role': u.role,
            }
            for u in users.order_by('role', 'first_name')[:500]
        ]
        return Response({'results': data})

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        """Pin a notice"""
        notice = self.get_object()
        notice.is_pinned = not notice.is_pinned
        notice.save()
        return Response({'status': f"notice {'pinned' if notice.is_pinned else 'unpinned'}"})

    @action(detail=False, methods=['post'], permission_classes=[CanManageNotices])
    def send_personal_notice(self, request):
        """Send personal notice to a specific student"""
        student_id = request.data.get('student_id')
        title = request.data.get('title')
        content = request.data.get('content')
        
        if not all([student_id, title, content]):
            return Response({'error': 'student_id, title, and content are required'}, status=400)
        
        try:
            student = User.objects.get(id=student_id, school=request.user.school, role='student', is_active=True)
        except User.DoesNotExist:
            return Response({'error': 'Student not found or not in your school'}, status=404)
        
        personal_notice = PersonalNotice.objects.create(
            school=request.user.school,
            student=student,
            created_by=request.user,
            title=title,
            content=content
        )

        # Email + in-app/FCM push to the individual student
        send_personal_notice_email.delay(personal_notice.id)
        send_personal_notice_push.delay(personal_notice.id)

        serializer = PersonalNoticeSerializer(personal_notice)
        return Response({
            'status': 'personal notice sent successfully',
            'notice': serializer.data
        })

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_personal_notices(self, request):
        """Get personal notices for the current student"""
        personal_notices = PersonalNotice.objects.filter(
            student=request.user,
            school=request.user.school
        ).select_related('created_by', 'school').order_by('-sent_at')
        
        serializer = PersonalNoticeSerializer(personal_notices, many=True)
        return Response(serializer.data)


class SMSConfigurationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = _school_for_request(request)
        if not school:
            return Response({"detail": "A school tenant is required."}, status=400)
        config, _ = SMSConfiguration.objects.get_or_create(school=school)
        return Response(SMSConfigurationSerializer(config).data)

    def patch(self, request):
        if request.user.role not in {"school_admin", "super_admin"}:
            return Response({"detail": "Only a school administrator can change SMS settings."}, status=403)
        school = _school_for_request(request)
        if not school:
            return Response({"detail": "A school tenant is required."}, status=400)
        config, _ = SMSConfiguration.objects.get_or_create(school=school)
        sender_id = request.data.get("sender_id")
        if sender_id is not None:
            sender_id = str(sender_id).strip().upper()
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9 ._-]{1,10}", sender_id):
                return Response({"detail": "Sender ID must contain 2-11 letters, numbers, spaces, dots, dashes or underscores."}, status=400)
            config.sender_id = sender_id
            config.sender_id_status = "pending"
            config.rejection_reason = ""
            config.is_enabled = False
        if "is_enabled" in request.data:
            if request.data["is_enabled"] and config.sender_id_status != "approved":
                return Response({"detail": "Your Sender ID has not been approved yet."}, status=400)
            config.is_enabled = bool(request.data["is_enabled"])
        config.save()
        _audit(request, "sms_sender_id_submitted", config, {"sender_id": config.sender_id})
        return Response(SMSConfigurationSerializer(config).data)


class SMSTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = SMSTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == "super_admin":
            school_id = self.request.query_params.get("school_id")
            return SMSTemplate.objects.filter(school_id=school_id) if school_id else SMSTemplate.objects.all()
        return SMSTemplate.objects.filter(school=self.request.user.school)

    def _can_write(self):
        return _is_sms_admin(self.request.user)

    def create(self, request, *args, **kwargs):
        if not self._can_write():
            return Response({"detail": "You do not have permission to manage SMS templates."}, status=403)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(school=request.user.school, created_by=request.user)
        _audit(request, "sms_template_created", obj)
        return Response(self.get_serializer(obj).data, status=201)

    def perform_update(self, serializer):
        serializer.save()
        _audit(self.request, "sms_template_updated", serializer.instance)

    def destroy(self, request, *args, **kwargs):
        if not self._can_write():
            return Response({"detail": "You do not have permission to manage SMS templates."}, status=403)
        obj = self.get_object()
        _audit(request, "sms_template_deleted", obj)
        return super().destroy(request, *args, **kwargs)


class SMSMessageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SMSMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = SMSMessage.objects.select_related("sent_by", "job")
        if self.request.user.role != "super_admin":
            qs = qs.filter(school=self.request.user.school)
        elif self.request.query_params.get("school_id"):
            qs = qs.filter(school_id=self.request.query_params["school_id"])
        for field in ("status", "sender_id", "category", "recipient"):
            if self.request.query_params.get(field):
                qs = qs.filter(**{f"{field}__icontains": self.request.query_params[field]})
        return qs


class SMSBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = _school_for_request(request)
        if not school:
            return Response({"detail": "A school tenant is required."}, status=400)
        balance, _ = SMSBalance.objects.get_or_create(school=school)
        return Response(SMSBalanceSerializer(balance).data)


def _resolve_recipients(request, school, payload):
    """Resolve only users belonging to the request tenant."""
    recipients = []
    audience = payload.get("audience")
    ids = payload.get("recipient_ids") or []
    if audience in {"all_parents", "all_teachers", "all_students"}:
        role = audience.replace("all_", "").rstrip("s")
        users = User.objects.filter(school=school, role=role, is_active=True).exclude(phone="")
    elif ids:
        users = User.objects.filter(school=school, id__in=ids, is_active=True).exclude(phone="")
    else:
        users = User.objects.none()
    for user in users:
        context = {
            "parent_name": user.get_full_name() or user.username,
            "student_name": user.get_full_name() or user.username,
            "teacher_name": user.get_full_name() or user.username,
            "school_name": school.name,
        }
        if user.role == "parent":
            relationship = user.parent_student_relationships.filter(
                status="approved", student__school=school
            ).select_related("student").first()
            if relationship:
                context["student_name"] = relationship.student.get_full_name() or relationship.student.username
        recipients.append({"phone": user.phone, "context": context})
    for phone in payload.get("custom_phone_numbers") or []:
        recipients.append({"phone": phone, "context": {"school_name": school.name}})
    return recipients


def _resolve_super_admin_recipients(school, audience, recipient_ids=None):
    """Resolve platform recipients while keeping each job tied to one school."""
    if audience == "all_school_admins":
        users = User.objects.filter(
            role="school_admin", is_active=True, school=school
        ).exclude(phone="")
    elif audience == "all_users":
        users = User.objects.filter(
            school=school, is_active=True
        ).exclude(phone="")
    elif audience in {"all_parents", "all_teachers", "all_students"}:
        role = audience.replace("all_", "").rstrip("s")
        users = User.objects.filter(
            school=school, role=role, is_active=True
        ).exclude(phone="")
    elif recipient_ids:
        users = User.objects.filter(
            school=school, id__in=recipient_ids, is_active=True
        ).exclude(phone="")
    else:
        users = User.objects.none()

    return [
        {
            "phone": user.phone,
            "context": {
                "parent_name": user.get_full_name() or user.username,
                "student_name": user.get_full_name() or user.username,
                "teacher_name": user.get_full_name() or user.username,
                "school_name": school.name,
            },
        }
        for user in users
    ]


class SMSSendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _is_sms_admin(request.user):
            return Response({"detail": "You do not have permission to send SMS."}, status=403)
        school = _school_for_request(request)
        if not school:
            return Response({"detail": "A school tenant is required."}, status=400)
        payload = request.data
        template = None
        if payload.get("template_id"):
            template = get_object_or_404(SMSTemplate, pk=payload["template_id"], school=school, is_active=True)
        message = payload.get("message") or (template.message if template else "")
        if not message or len(message) > 5000:
            return Response({"detail": "A message between 1 and 5,000 characters is required."}, status=400)
        recipients = _resolve_recipients(request, school, payload)
        # A caller may supply explicit contexts for API integrations, but never
        # arbitrary expressions or code.
        if payload.get("variables") and not recipients:
            recipients = [{"phone": p, "context": payload["variables"]} for p in payload.get("custom_phone_numbers", [])]
        key = request.headers.get("Idempotency-Key") or payload.get("idempotency_key", "")
        try:
            job, created = send_sms(
                school=school, recipients=recipients, message=message,
                triggered_by=request.user, category=payload.get("category") or (template.category if template else "custom"),
                idempotency_key=key[:128],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(SMSJobSerializer(job).data, status=202 if created else 200)


class AdminSMSSendView(APIView):
    """Send SMS from the platform console on behalf of one or more schools."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != "super_admin":
            return Response({"detail": "Super Admin access is required."}, status=403)

        payload = request.data
        message = str(payload.get("message") or "").strip()
        audience = payload.get("audience", "all_school_admins")
        if not message or len(message) > 5000:
            return Response(
                {"detail": "A message between 1 and 5,000 characters is required."},
                status=400,
            )
        allowed_audiences = {
            "all_school_admins", "all_users", "all_parents",
            "all_teachers", "all_students", "custom",
        }
        if audience not in allowed_audiences:
            return Response({"detail": "Unsupported SMS audience."}, status=400)

        school_id = payload.get("school_id")
        if school_id:
            schools = [get_object_or_404(School, pk=school_id)]
        elif audience == "all_school_admins":
            schools = list(School.objects.filter(status__in=["active", "trial"]).order_by("id"))
        else:
            return Response(
                {"detail": "Select a school for this audience."}, status=400
            )

        results = []
        failures = []
        custom_numbers = payload.get("custom_phone_numbers") or []
        for school in schools:
            recipients = _resolve_super_admin_recipients(
                school, audience, payload.get("recipient_ids") or []
            )
            if audience == "custom":
                recipients = [
                    {"phone": phone, "context": {"school_name": school.name}}
                    for phone in custom_numbers
                ]
            try:
                job, created = send_sms(
                    school=school,
                    recipients=recipients,
                    message=message,
                    triggered_by=request.user,
                    category=payload.get("category", "custom"),
                    idempotency_key=(
                        f"{payload.get('idempotency_key', '')}:{school.pk}"
                        if payload.get("idempotency_key")
                        else ""
                    )[:128],
                )
                results.append({
                    "school_id": school.pk,
                    "school": school.name,
                    "job": SMSJobSerializer(job).data,
                    "created": created,
                })
            except ValueError as exc:
                failures.append({
                    "school_id": school.pk,
                    "school": school.name,
                    "detail": str(exc),
                })

        if not results and failures:
            return Response(
                {
                    "detail": "No SMS jobs were created. "
                    + "; ".join(
                        f"{failure['school']}: {failure['detail']}"
                        for failure in failures[:5]
                    ),
                    "failures": failures,
                },
                status=400,
            )
        _audit(
            request,
            "admin_sms_sent",
            request.user,
            {"jobs": len(results), "failures": len(failures), "audience": audience},
        )
        return Response(
            {"jobs": results, "failures": failures},
            status=202 if results else 400,
        )


class SMSDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = _school_for_request(request)
        qs = SMSMessage.objects.filter(school=school) if school else SMSMessage.objects.none()
        balance, _ = SMSBalance.objects.get_or_create(school=school) if school else (None, False)
        return Response({
            "balance": balance.credits if balance else 0,
            "sent": qs.filter(status__in=["sent", "delivered"]).count(),
            "delivered": qs.filter(status="delivered").count(),
            "failed": qs.filter(status="failed").count(),
            "credits_used": qs.aggregate(total=Sum("credits_used"))["total"] or 0,
            "recent": SMSMessageSerializer(qs[:10], many=True).data,
        })


class SMSWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        secret = os.environ.get("ARKESEL_WEBHOOK_SECRET", "")
        supplied = request.headers.get("X-Arkesel-Signature", "")
        if not secret or not hmac.compare_digest(supplied, secret):
            return Response({"detail": "Invalid webhook signature."}, status=403)
        data = request.data
        provider_id = str(data.get("message_id") or data.get("messageId") or data.get("id") or "")
        if not provider_id:
            return Response({"detail": "Invalid webhook payload."}, status=400)
        state = str(data.get("status", "")).lower()
        status_map = {"delivered": "delivered", "success": "delivered", "sent": "sent", "failed": "failed", "error": "failed"}
        new_status = status_map.get(state)
        if not new_status:
            return Response({"detail": "Unsupported delivery status."}, status=400)
        updated = SMSMessage.objects.filter(provider_message_id=provider_id).update(
            status=new_status, delivered_at=timezone.now() if new_status == "delivered" else None,
            error_message=str(data.get("error", "")) if new_status == "failed" else "",
        )
        return Response({"updated": updated})


class AdminSMSSenderRequestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SMSConfigurationSerializer
    permission_classes = [IsAuthenticated]
    queryset = SMSConfiguration.objects.select_related("school").all()

    def initial(self, request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != "super_admin":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Super Admin access is required.")
        return super().initial(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = self.get_object()
        obj.sender_id_status, obj.rejection_reason = "approved", ""
        obj.is_enabled = True
        obj.save(update_fields=["sender_id_status", "rejection_reason", "is_enabled", "updated_at"])
        _audit(request, "sms_sender_id_approved", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        obj = self.get_object()
        obj.sender_id_status = "rejected"
        obj.rejection_reason = str(request.data.get("reason", "Sender ID was not approved."))
        obj.is_enabled = False
        obj.save(update_fields=["sender_id_status", "rejection_reason", "is_enabled", "updated_at"])
        _audit(request, "sms_sender_id_rejected", obj, {"reason": obj.rejection_reason})
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        obj = self.get_object()
        obj.sender_id_status, obj.is_enabled = "disabled", False
        obj.save(update_fields=["sender_id_status", "is_enabled", "updated_at"])
        _audit(request, "sms_sender_id_disabled", obj)
        return Response(self.get_serializer(obj).data)


class AdminSMSBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != "super_admin":
            return Response({"detail": "Super Admin access is required."}, status=403)
        school = get_object_or_404(School, pk=request.data.get("school_id"))
        amount = int(request.data.get("amount", 0))
        if amount < 1:
            return Response({"detail": "Amount must be positive."}, status=400)
        with transaction.atomic():
            balance, _ = SMSBalance.objects.select_for_update().get_or_create(school=school)
            balance.credits += amount
            balance.save(update_fields=["credits", "updated_at"])
            SMSCreditLedger.objects.create(
                school=school, amount=amount, balance_after=balance.credits,
                reason="admin_adjustment", actor=request.user,
            )
        _audit(request, "sms_credits_added", balance, {"amount": amount})
        return Response(SMSBalanceSerializer(balance).data)


class AdminSMSDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "super_admin":
            return Response({"detail": "Super Admin access is required."}, status=403)
        messages = SMSMessage.objects.all()
        rows = []
        for school in School.objects.all().order_by("name"):
            balance = SMSBalance.objects.filter(school=school).first()
            school_messages = messages.filter(school=school)
            last = school_messages.order_by("-created_at").first()
            config = SMSConfiguration.objects.filter(school=school).first()
            rows.append({
                "school": school.name, "school_id": school.pk,
                "configuration_id": config.pk if config else None,
                "sender_id": config.sender_id if config else "",
                "sender_id_status": config.sender_id_status if config else "pending",
                "balance": balance.credits if balance else 0,
                "sent": school_messages.filter(status__in=["sent", "delivered"]).count(),
                "last_sms": last.created_at if last else None,
            })
        return Response({
            "total_sent": messages.filter(status__in=["sent", "delivered"]).count(),
            "total_credits_used": messages.aggregate(total=Sum("credits_used"))["total"] or 0,
            "total_failed": messages.filter(status="failed").count(),
            "pending_approvals": SMSConfiguration.objects.filter(sender_id_status="pending").count(),
            "schools": rows,
        })
