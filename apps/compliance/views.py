from django.core.files.storage import default_storage
from django.db import models, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schools.models import School
from .models import (
    ComplianceProfile,
    ComplianceRequirement,
    ComplianceStatus,
    ComplianceDocument,
    ComplianceDocumentVersion,
    RequirementStatus,
    SchoolComplianceRequirement,
    ApprovalMethod,
    Agreement,
    AgreementAcceptance,
)


def school_for(request):
    return getattr(request.user, "school", None)


def ensure_checklist(school):
    profile, _ = ComplianceProfile.objects.get_or_create(school=school)
    for requirement in ComplianceRequirement.objects.filter(is_active=True):
        if not requirement.applies_to(getattr(school, "school_type", None)):
            applicable = False
        else:
            applicable = True
        SchoolComplianceRequirement.objects.get_or_create(
            school=school,
            profile=profile,
            requirement=requirement,
            defaults={"is_applicable": applicable, "sort_order": requirement.sort_order},
        )
    return profile


def requirement_payload(item):
    prefetched_documents = getattr(item, "_prefetched_objects_cache", {}).get("documents")
    document = next((doc for doc in prefetched_documents or [] if doc.is_current), None)
    if document is None and prefetched_documents is None:
        document = item.current_document()
    agreement = None
    if item.requirement.requirement_type == "agreement" and item.requirement.agreement_code:
        agreement = Agreement.objects.filter(
            code=item.requirement.agreement_code, is_active=True
        ).first()
    return {
        "id": item.id,
        "requirement_id": item.requirement_id,
        "code": item.requirement.code,
        "name": item.requirement.name,
        "description": item.requirement.description,
        "requirement_type": item.requirement.requirement_type,
        "is_mandatory": item.requirement.is_mandatory,
        "status": item.status,
        "is_applicable": item.is_applicable,
        "information": item.information,
        "information_schema": item.requirement.information_schema,
        "document": {
            "id": document.id,
            "file_name": document.file_name,
            "file_url": document.file_url,
            "document_number": document.document_number,
            "issue_date": document.issue_date,
            "expiry_date": document.expiry_date,
        } if document else None,
        "reason": item.requirement_reason(),
        "agreement": {
            "id": agreement.id,
            "code": agreement.code,
            "title": agreement.title,
            "version": agreement.version,
            "summary": agreement.summary,
            "body": agreement.body,
        } if agreement else None,
    }


def profile_payload(profile):
    items = list(profile.requirements.select_related("requirement").prefetch_related("documents"))
    applicable = [item for item in items if item.is_applicable]
    resolved = sum(item.status in {"approved", "bypassed"} for item in applicable)
    return {
        "id": profile.id,
        "school_id": profile.school_id,
        "status": profile.status,
        "school_status": profile.school.status,
        "compliance_status": getattr(profile.school, "compliance_status", None),
        "approval_method": profile.approval_method,
        "approved_at": profile.approved_at,
        "total_requirements": len(applicable),
        "resolved_count": resolved,
        "progress_percent": round((resolved / len(applicable)) * 100) if applicable else 0,
        "requirements": [requirement_payload(item) for item in items],
        "submitted_at": profile.submitted_at,
        "rejection_reason": profile.rejection_reason,
    }


class ComplianceStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        school = school_for(request)
        if not school:
            return Response(
                {'school_status': None, 'compliance_status': None, 'needs_compliance': False},
                status=status.HTTP_200_OK,
            )

        profile = ensure_checklist(school)
        data = profile_payload(profile)
        return Response({
            'school_id': school.id,
            'school_status': school.status,
            'compliance_status': getattr(school, 'compliance_status', 'not_started'),
            'needs_compliance': school.status != 'active' or profile.status != ComplianceStatus.APPROVED,
            'profile': data,
        })


class ComplianceProfileView(ComplianceStatusView):
    def get(self, request, *args, **kwargs):
        school = school_for(request)
        if not school:
            return Response({"detail": "A school account is required."}, status=400)
        profile = ensure_checklist(school)
        return Response(profile_payload(profile))

    def patch(self, request, *args, **kwargs):
        school = school_for(request)
        if not school:
            return Response({"detail": "A school account is required."}, status=400)
        profile = ensure_checklist(school)
        item_id = request.data.get("requirement_id")
        item = profile.requirements.filter(pk=item_id).select_related("requirement").first()
        if not item:
            return Response({"detail": "Compliance requirement not found."}, status=404)
        if item.status in {"submitted", "under_review", "approved", "bypassed"}:
            return Response({"detail": "This requirement is not currently editable."}, status=400)
        item.information = request.data.get("information", item.information)
        item.status = RequirementStatus.IN_PROGRESS
        item.save(update_fields=["information", "status", "updated_at"])
        school.compliance_status = ComplianceStatus.IN_PROGRESS
        school.save(update_fields=["compliance_status", "updated_at"])
        return Response(profile_payload(profile))

    def post(self, request, *args, **kwargs):
        school = school_for(request)
        if not school:
            return Response({"detail": "A school account is required."}, status=400)
        profile = ensure_checklist(school)
        now = timezone.now()
        profile.requirements.filter(
            is_applicable=True,
            status=RequirementStatus.IN_PROGRESS,
        ).update(
            status=RequirementStatus.SUBMITTED,
            submitted_at=now,
            updated_at=now,
        )
        profile.status = ComplianceStatus.SUBMITTED
        profile.submitted_at = now
        profile.last_submitted_by = request.user
        profile.save(update_fields=["status", "submitted_at", "last_submitted_by", "updated_at"])
        school.compliance_status = ComplianceStatus.SUBMITTED
        school.save(update_fields=["compliance_status", "updated_at"])
        return Response(profile_payload(profile))


class AgreementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agreement = Agreement.objects.filter(
            code="alara_school_agreement", is_active=True
        ).first()
        if not agreement:
            return Response({"detail": "The Alara School Agreement has not been published yet."}, status=404)
        return Response({
            "id": agreement.id,
            "code": agreement.code,
            "title": agreement.title,
            "version": agreement.version,
            "summary": agreement.summary,
            "body": agreement.body,
        })

    def put(self, request):
        if request.user.role != "super_admin":
            return Response({"detail": "Super Admin access required."}, status=403)
        agreement, _ = Agreement.objects.get_or_create(
            code="alara_school_agreement",
            defaults={"title": "Alara School Agreement"},
        )
        agreement.title = request.data.get("title", agreement.title)
        agreement.summary = request.data.get("summary", agreement.summary)
        agreement.body = request.data.get("body", agreement.body)
        agreement.version = request.data.get("version", agreement.version)
        agreement.is_active = True
        agreement.save()
        return Response({
            "id": agreement.id, "code": agreement.code, "title": agreement.title,
            "version": agreement.version, "summary": agreement.summary, "body": agreement.body,
        })


class AgreementDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = school_for(request)
        if not school:
            return Response({"detail": "A school account is required."}, status=400)
        decision = request.data.get("decision")
        if decision not in {"accept", "reject"}:
            return Response({"detail": "decision must be accept or reject."}, status=400)
        agreement = Agreement.objects.filter(
            code="alara_school_agreement", is_active=True
        ).first()
        if not agreement:
            return Response({"detail": "The Alara School Agreement has not been published yet."}, status=404)
        profile = ensure_checklist(school)
        item = profile.requirements.filter(
            requirement__agreement_code=agreement.code
        ).first()
        if not item:
            return Response({"detail": "Agreement requirement is not configured."}, status=404)
        if decision == "accept":
            AgreementAcceptance.objects.update_or_create(
                agreement=agreement, school=school, version=agreement.version,
                defaults={
                    "user": request.user,
                    "ip_address": request.META.get("REMOTE_ADDR", ""),
                    "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                },
            )
            item.status = RequirementStatus.APPROVED
            item.agreement_version = agreement.version
            item.agreement_accepted_at = timezone.now()
            item.agreement_accepted_by = request.user
        else:
            item.status = RequirementStatus.REJECTED
            item.rejection_reason = "Agreement rejected by school administrator."
        item.save(update_fields=[
            "status", "agreement_version", "agreement_accepted_at",
            "agreement_accepted_by", "rejection_reason", "updated_at",
        ])
        school.compliance_status = ComplianceStatus.IN_PROGRESS
        school.save(update_fields=["compliance_status", "updated_at"])
        return Response(profile_payload(profile))

class ComplianceDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = school_for(request)
        profile = ensure_checklist(school) if school else None
        if not profile:
            return Response({"detail": "A school account is required."}, status=400)
        item = profile.requirements.filter(pk=request.data.get("requirement_id")).select_related("requirement").first()
        upload = request.FILES.get("file")
        if not item or not upload:
            return Response({"detail": "requirement_id and file are required."}, status=400)
        path = default_storage.save(f"compliance/{school.id}/{upload.name}", upload)
        url = default_storage.url(path)
        with transaction.atomic():
            ComplianceDocument.objects.filter(school_requirement=item, is_current=True).update(is_current=False)
            document = ComplianceDocument.objects.create(
                school=school, school_requirement=item, file_name=upload.name,
                file_url=url, storage_path=path, mime_type=upload.content_type or "",
                file_size=upload.size, uploaded_by=request.user,
            )
            ComplianceDocumentVersion.objects.create(
                document=document, school=school, school_requirement=item,
                version=document.id, file_name=document.file_name, file_url=url,
                storage_path=path, mime_type=document.mime_type, file_size=document.file_size,
                uploaded_by=request.user,
            )
            item.status = RequirementStatus.IN_PROGRESS
            item.save(update_fields=["status", "updated_at"])
        school.compliance_status = ComplianceStatus.IN_PROGRESS
        school.save(update_fields=["compliance_status", "updated_at"])
        return Response(profile_payload(profile), status=201)


class ComplianceAdminQueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "super_admin":
            return Response({"detail": "Super Admin access required."}, status=403)
        candidate_schools = School.objects.filter(
            models.Q(status__in=["pending_compliance", "rejected"]) |
            ~models.Q(compliance_status=ComplianceStatus.APPROVED)
        )
        for school in candidate_schools.iterator():
            ensure_checklist(school)
        profiles = ComplianceProfile.objects.filter(
            models.Q(school__status__in=["pending_compliance", "rejected"]) |
            ~models.Q(status=ComplianceStatus.APPROVED)
        ).select_related("school").prefetch_related("requirements__requirement", "requirements__documents")
        return Response([{
            "school_id": profile.school_id,
            "school_name": profile.school.name,
            "school_email": profile.school.email,
            "school_status": profile.school.status,
            **profile_payload(profile),
        } for profile in profiles])


class ComplianceDocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "super_admin":
            return Response({"detail": "Super Admin access required."}, status=403)
        for school in School.objects.filter(compliance_profile__isnull=True).iterator():
            ensure_checklist(school)
        profiles = ComplianceProfile.objects.select_related("school").prefetch_related(
            "requirements__requirement", "requirements__documents"
        ).all()
        return Response([{
            "school_id": profile.school_id,
            "school_name": profile.school.name,
            "school_email": profile.school.email,
            "school_status": profile.school.status,
            **profile_payload(profile),
        } for profile in profiles])


class ComplianceAdminReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def _profile(self, request, school_id):
        if request.user.role != "super_admin":
            return None
        school = School.objects.filter(pk=school_id).first()
        if not school:
            return None
        return ensure_checklist(school)

    def get(self, request, school_id):
        profile = self._profile(request, school_id)
        if not profile:
            return Response({"detail": "School not found or access denied."}, status=404)
        return Response(profile_payload(profile))

    def post(self, request, school_id):
        with transaction.atomic():
            profile = self._profile(request, school_id)
            if not profile:
                return Response({"detail": "School not found or access denied."}, status=404)
            item = profile.requirements.filter(pk=request.data.get("requirement_id")).first()
            decision = request.data.get("decision")
            if not item or decision not in {"approve", "reject"}:
                return Response({"detail": "A valid requirement_id and decision are required."}, status=400)
            now = timezone.now()
            item.reviewed_by = request.user
            item.reviewed_at = now
            item.review_notes = request.data.get("notes", "")
            item.status = RequirementStatus.APPROVED if decision == "approve" else RequirementStatus.REJECTED
            if decision == "reject":
                item.rejection_reason = item.review_notes or "Rejected by Super Admin."
            item.save(update_fields=[
                "status", "reviewed_by", "reviewed_at", "review_notes",
                "rejection_reason", "updated_at",
            ])
            remaining = profile.requirements.filter(is_applicable=True).exclude(
                status__in=[RequirementStatus.APPROVED, RequirementStatus.BYPASSED]
            ).exists()
            school = profile.school
            if not remaining:
                profile.status = ComplianceStatus.APPROVED
                profile.approval_method = ApprovalMethod.FULLY_COMPLIANT
                profile.reviewed_at = now
                profile.reviewed_by = request.user
                profile.approved_at = now
                profile.approved_by = request.user
                profile.save(update_fields=[
                    "status", "approval_method", "reviewed_at", "reviewed_by",
                    "approved_at", "approved_by", "updated_at",
                ])
                school.status = "active"
                school.compliance_status = ComplianceStatus.APPROVED
                school.approved_at = now
                school.approved_by = request.user
                school.approval_method = ApprovalMethod.FULLY_COMPLIANT
                school.save(update_fields=[
                    "status", "compliance_status", "approved_at", "approved_by",
                    "approval_method", "updated_at",
                ])
            elif decision == "reject":
                profile.status = ComplianceStatus.REQUIRES_RESUBMISSION
                profile.save(update_fields=["status", "updated_at"])
        return Response(profile_payload(profile))


class ComplianceAdminApproveAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, school_id):
        if request.user.role != "super_admin":
            return Response({"detail": "Super Admin access is required."}, status=403)

        with transaction.atomic():
            school = School.objects.select_for_update().filter(pk=school_id).first()
            if not school:
                return Response({"detail": "School not found."}, status=404)

            profile = ensure_checklist(school)
            now = timezone.now()
            unresolved = profile.requirements.filter(is_applicable=True).exclude(
                status__in=[RequirementStatus.APPROVED, RequirementStatus.BYPASSED]
            )
            unresolved.update(
                status=RequirementStatus.BYPASSED,
                reviewed_by=request.user,
                reviewed_at=now,
                review_notes="Account approved by Super Admin.",
                updated_at=now,
            )
            has_overrides = profile.requirements.filter(
                is_applicable=True, status=RequirementStatus.BYPASSED
            ).exists()
            approval_method = (
                ApprovalMethod.APPROVED_WITH_OVERRIDES
                if has_overrides
                else ApprovalMethod.FULLY_COMPLIANT
            )
            profile.status = ComplianceStatus.APPROVED
            profile.approval_method = approval_method
            profile.reviewed_at = now
            profile.reviewed_by = request.user
            profile.approved_at = now
            profile.approved_by = request.user
            profile.save(update_fields=[
                "status", "approval_method", "reviewed_at", "reviewed_by",
                "approved_at", "approved_by", "updated_at",
            ])

            school.status = "active"
            school.compliance_status = ComplianceStatus.APPROVED
            school.approved_at = now
            school.approved_by = request.user
            school.approval_method = approval_method
            school.save(update_fields=[
                "status", "compliance_status", "approved_at", "approved_by",
                "approval_method", "updated_at",
            ])

        return Response(profile_payload(profile))
