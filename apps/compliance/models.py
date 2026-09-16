"""
School Compliance models.

Schema is created by ``backend/compliance_migration.sql`` (no Django
migrations — same pattern as ``apps.platform`` and the promotion schema).
Every table is pinned with an explicit ``db_table`` so the ORM matches the SQL.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Status vocabularies
# ---------------------------------------------------------------------------

class ComplianceStatus(models.TextChoices):
    """Overall compliance status of a school."""
    PENDING = 'pending', 'Pending'
    IN_PROGRESS = 'in_progress', 'In Progress'
    SUBMITTED = 'submitted', 'Submitted'
    UNDER_REVIEW = 'under_review', 'Under Review'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    REQUIRES_RESUBMISSION = 'requires_resubmission', 'Requires Resubmission'


class RequirementStatus(models.TextChoices):
    """Status of a single per-school requirement."""
    NOT_STARTED = 'not_started', 'Not Started'
    IN_PROGRESS = 'in_progress', 'In Progress'
    SUBMITTED = 'submitted', 'Submitted'
    UNDER_REVIEW = 'under_review', 'Under Review'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    BYPASSED = 'bypassed', 'Bypassed'
    REQUIRES_RESUBMISSION = 'requires_resubmission', 'Requires Resubmission'


class RequirementType(models.TextChoices):
    DOCUMENT = 'document', 'Document'
    INFORMATION = 'information', 'Information'
    AGREEMENT = 'agreement', 'Agreement'


class ApprovalMethod(models.TextChoices):
    FULLY_COMPLIANT = 'fully_compliant', 'Fully Compliant'
    APPROVED_WITH_OVERRIDES = 'approved_with_overrides', 'Approved With Compliance Overrides'


#: Requirement statuses that count as "done" for progress purposes.
RESOLVED_STATUSES = frozenset({RequirementStatus.APPROVED, RequirementStatus.BYPASSED})
#: Requirement statuses that still need work from the school.
OPEN_STATUSES = frozenset({
    RequirementStatus.NOT_STARTED,
    RequirementStatus.IN_PROGRESS,
    RequirementStatus.REJECTED,
    RequirementStatus.REQUIRES_RESUBMISSION,
})
#: Requirement statuses that are locked from casual school editing.
LOCKED_FOR_SCHOOL = frozenset({
    RequirementStatus.SUBMITTED,
    RequirementStatus.UNDER_REVIEW,
    RequirementStatus.APPROVED,
    RequirementStatus.BYPASSED,
})

#: Requirement status a school may edit/resubmit from.
EDITABLE_STATUSES = frozenset({
    RequirementStatus.NOT_STARTED,
    RequirementStatus.IN_PROGRESS,
    RequirementStatus.REJECTED,
    RequirementStatus.REQUIRES_RESUBMISSION,
})


class DocumentStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    EXPIRING_SOON = 'expiring_soon', 'Expiring Soon'
    EXPIRED = 'expired', 'Expired'
    NO_EXPIRY = 'no_expiry', 'No Expiry'


# ---------------------------------------------------------------------------
# 1. Requirement catalog
# ---------------------------------------------------------------------------

class ComplianceRequirement(models.Model):
    """A *type* of thing every (matching) school must provide.

    Managed by the Super Admin. Requirements added after a school's
    onboarding are seeded onto that school's checklist as ``not_started``.
    """
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    requirement_type = models.CharField(
        max_length=20, choices=RequirementType.choices, default=RequirementType.DOCUMENT)
    institution_types = models.JSONField(
        default=list, blank=True,
        help_text='Empty list = applies to every institution type.')
    is_mandatory = models.BooleanField(default=True)
    has_expiry = models.BooleanField(default=False)
    requires_document_number = models.BooleanField(default=False)
    requires_issue_date = models.BooleanField(default=False)
    information_schema = models.JSONField(
        default=list, blank=True,
        help_text='Field definitions for information-type requirements.')
    agreement_code = models.CharField(max_length=80, blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compliance_requirement'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name

    def applies_to(self, institution_type=None):
        """True when this requirement applies to the given institution type."""
        if not self.institution_types:
            return True
        if not institution_type:
            return True
        return institution_type in self.institution_types


# ---------------------------------------------------------------------------
# 2. Compliance profile (one per school)
# ---------------------------------------------------------------------------

class ComplianceProfile(models.Model):
    school = models.OneToOneField(
        'schools.School', on_delete=models.CASCADE, related_name='compliance_profile')
    status = models.CharField(
        max_length=30, choices=ComplianceStatus.choices, default=ComplianceStatus.PENDING)
    total_requirements = models.IntegerField(default=0)
    approved_count = models.IntegerField(default=0)
    bypassed_count = models.IntegerField(default=0)
    rejected_count = models.IntegerField(default=0)
    pending_count = models.IntegerField(default=0)
    approval_method = models.CharField(
        max_length=30, choices=ApprovalMethod.choices, blank=True, null=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    review_started_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_profiles_reviewed')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_profiles_approved')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_profiles_rejected')
    rejection_reason = models.TextField(blank=True, default='')
    last_submitted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_profiles_submitted')
    renewal_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compliance_profile'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.school_id} · {self.status}'

    # ── Derived helpers ────────────────────────────────────────────────
    @property
    def is_approved(self):
        return self.status == ComplianceStatus.APPROVED

    @property
    def has_overrides(self):
        return self.approval_method == ApprovalMethod.APPROVED_WITH_OVERRIDES

    def applicable_requirements(self):
        return self.school.requirement_instances.filter(is_applicable=True)

    def display_badge(self):
        """The approval badge shown to the Super Admin (brief §29)."""
        if self.status != ComplianceStatus.APPROVED:
            return self.get_status_display()
        if self.has_overrides:
            return 'Approved With Compliance Overrides'
        return 'Fully Verified'


# ---------------------------------------------------------------------------
# 3. Per-school requirement instance
# ---------------------------------------------------------------------------

class SchoolComplianceRequirement(models.Model):
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='requirement_instances')
    profile = models.ForeignKey(
        ComplianceProfile, on_delete=models.CASCADE, related_name='requirements')
    requirement = models.ForeignKey(
        ComplianceRequirement, on_delete=models.CASCADE, related_name='school_instances')
    status = models.CharField(
        max_length=30, choices=RequirementStatus.choices,
        default=RequirementStatus.NOT_STARTED)
    is_applicable = models.BooleanField(default=True)
    information = models.JSONField(default=dict, blank=True)
    agreement_version = models.CharField(max_length=30, blank=True, default='')
    agreement_accepted_at = models.DateTimeField(null=True, blank=True)
    agreement_accepted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_agreements_accepted')
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_requirements_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default='')
    rejection_reason = models.TextField(blank=True, default='')
    previous_status = models.CharField(max_length=30, blank=True, default='')
    resubmission_requested_at = models.DateTimeField(null=True, blank=True)
    resubmission_reason = models.TextField(blank=True, default='')
    bypassed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_requirements_bypassed')
    bypassed_at = models.DateTimeField(null=True, blank=True)
    bypass_reason = models.TextField(blank=True, default='')
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'school_compliance_requirement'
        ordering = ['sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'requirement'],
                name='uq_school_compliance_requirement'),
        ]

    def __str__(self):
        return f'{self.requirement.name} · {self.status}'

    @property
    def name(self):
        return self.requirement.name

    @property
    def is_resolved(self):
        return self.status in RESOLVED_STATUSES

    @property
    def is_editable_by_school(self):
        return self.status in EDITABLE_STATUSES or self.status == RequirementStatus.NOT_STARTED

    @property
    def is_bypassed(self):
        return self.status == RequirementStatus.BYPASSED

    @property
    def action_required(self):
        return self.status in (RequirementStatus.REJECTED,
                               RequirementStatus.REQUIRES_RESUBMISSION)

    def current_document(self):
        return self.documents.filter(is_current=True).order_by('-created_at').first()

    def requirement_reason(self):
        """Reason shown back to the school for the current state."""
        if self.status in (RequirementStatus.REJECTED, RequirementStatus.REQUIRES_RESUBMISSION):
            return self.rejection_reason or self.resubmission_reason
        return ''

    def document_status(self):
        """Active / Expiring Soon / Expired for the current document (brief §23)."""
        document = self.current_document()
        if not document or not document.expiry_date:
            return DocumentStatus.NO_EXPIRY
        return document.compute_status()


# ---------------------------------------------------------------------------
# 4. Compliance document (current)
# ---------------------------------------------------------------------------

class ComplianceDocument(models.Model):
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='compliance_documents')
    school_requirement = models.ForeignKey(
        SchoolComplianceRequirement, on_delete=models.CASCADE, related_name='documents')
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_url = models.TextField(blank=True, default='')
    storage_path = models.TextField(blank=True, default='')
    bucket = models.CharField(max_length=80, blank=True, default='compliance-documents')
    mime_type = models.CharField(max_length=120, blank=True, default='')
    file_size = models.BigIntegerField(default=0)
    document_number = models.CharField(max_length=120, blank=True, default='')
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_documents_uploaded')
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compliance_document'
        ordering = ['-created_at']

    def __str__(self):
        return self.file_name or f'document #{self.pk}'

    def compute_status(self, warn_days=30):
        """DocumentStatus for this document's expiry date."""
        if not self.expiry_date:
            return DocumentStatus.NO_EXPIRY
        today = timezone.localdate()
        if self.expiry_date < today:
            return DocumentStatus.EXPIRED
        if (self.expiry_date - today).days <= warn_days:
            return DocumentStatus.EXPIRING_SOON
        return DocumentStatus.ACTIVE


# ---------------------------------------------------------------------------
# 5. Document version history (immutable)
# ---------------------------------------------------------------------------

class ComplianceDocumentVersion(models.Model):
    document = models.ForeignKey(
        ComplianceDocument, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='versions')
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='compliance_document_versions')
    school_requirement = models.ForeignKey(
        SchoolComplianceRequirement, on_delete=models.CASCADE,
        related_name='document_versions')
    version = models.IntegerField(default=1)
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_url = models.TextField(blank=True, default='')
    storage_path = models.TextField(blank=True, default='')
    bucket = models.CharField(max_length=80, blank=True, default='compliance-documents')
    mime_type = models.CharField(max_length=120, blank=True, default='')
    file_size = models.BigIntegerField(default=0)
    document_number = models.CharField(max_length=120, blank=True, default='')
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_document_versions_uploaded')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    review_status = models.CharField(max_length=30, blank=True, default='submitted')
    review_notes = models.TextField(blank=True, default='')
    replaced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'compliance_document_version'
        ordering = ['-version', '-uploaded_at']

    def __str__(self):
        return f'{self.school_requirement_id} v{self.version}'


# ---------------------------------------------------------------------------
# 6. Compliance review (one row per reviewer decision)
# ---------------------------------------------------------------------------

class ComplianceReview(models.Model):
    ACTION_CHOICES = (
        ('submit', 'Submitted'),
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
        ('request_resubmission', 'Resubmission Requested'),
        ('bypass', 'Bypassed'),
        ('bypass_all', 'All Remaining Bypassed'),
        ('approve_school', 'School Approved'),
        ('reject_school', 'School Rejected'),
        ('suspend', 'School Suspended'),
    )

    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='compliance_reviews')
    profile = models.ForeignKey(
        ComplianceProfile, on_delete=models.CASCADE, related_name='reviews')
    school_requirement = models.ForeignKey(
        SchoolComplianceRequirement, on_delete=models.CASCADE,
        null=True, blank=True, related_name='reviews')
    document = models.ForeignKey(
        ComplianceDocument, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviews')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    previous_status = models.CharField(max_length=30, blank=True, default='')
    new_status = models.CharField(max_length=30, blank=True, default='')
    reason = models.TextField(blank=True, default='')
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_reviews_made')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'compliance_review'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} · {self.school_id}'


# ---------------------------------------------------------------------------
# 7. Compliance audit log (append-only)
# ---------------------------------------------------------------------------

class ComplianceAuditLog(models.Model):
    ACTION_SCHOOL_CREATED = 'school_created'
    ACTION_COMPLIANCE_STARTED = 'compliance_started'
    ACTION_DOCUMENT_UPLOADED = 'document_uploaded'
    ACTION_INFORMATION_UPDATED = 'information_updated'
    ACTION_AGREEMENT_ACCEPTED = 'agreement_accepted'
    ACTION_COMPLIANCE_SUBMITTED = 'compliance_submitted'
    ACTION_DOCUMENT_APPROVED = 'document_approved'
    ACTION_DOCUMENT_REJECTED = 'document_rejected'
    ACTION_RESUBMISSION_REQUESTED = 'resubmission_requested'
    ACTION_REQUIREMENT_BYPASSED = 'requirement_bypassed'
    ACTION_ALL_REQUIREMENTS_BYPASSED = 'all_requirements_bypassed'
    ACTION_SCHOOL_APPROVED = 'school_approved'
    ACTION_SCHOOL_REJECTED = 'school_rejected'
    ACTION_SCHOOL_SUSPENDED = 'school_suspended'
    ACTION_INFO_REQUESTED = 'info_requested'
    ACTION_INFO_RESPONDED = 'info_responded'
    ACTION_REQUIREMENT_ADDED = 'requirement_added'

    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='compliance_audit_logs')
    school_name = models.CharField(max_length=255, blank=True, default='')
    requirement = models.ForeignKey(
        ComplianceRequirement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs')
    requirement_name = models.CharField(max_length=255, blank=True, default='')
    school_requirement = models.ForeignKey(
        SchoolComplianceRequirement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs')
    action = models.CharField(max_length=60)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_audit_logs')
    actor_name = models.CharField(max_length=150, blank=True, default='')
    actor_role = models.CharField(max_length=40, blank=True, default='')
    previous_status = models.CharField(max_length=30, blank=True, default='')
    new_status = models.CharField(max_length=30, blank=True, default='')
    reason = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'compliance_audit_log'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} · {self.school_name}'


# ---------------------------------------------------------------------------
# 8. Information request (super admin -> school)
# ---------------------------------------------------------------------------

class ComplianceInformationRequest(models.Model):
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('responded', 'Responded'),
        ('closed', 'Closed'),
    )

    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='compliance_information_requests')
    school_requirement = models.ForeignKey(
        SchoolComplianceRequirement, on_delete=models.CASCADE,
        null=True, blank=True, related_name='information_requests')
    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_information_requested')
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default='')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    response = models.TextField(blank=True, default='')
    responded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_information_responded')
    responded_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='compliance_information_closed')
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compliance_information_request'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# 9. Agreement catalog
# ---------------------------------------------------------------------------

class Agreement(models.Model):
    code = models.CharField(max_length=80, unique=True)
    title = models.CharField(max_length=255)
    version = models.CharField(max_length=30, default='1.0')
    body = models.TextField(blank=True, default='')
    summary = models.TextField(blank=True, default='')
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compliance_agreement'
        ordering = ['title']

    def __str__(self):
        return f'{self.title} v{self.version}'


# ---------------------------------------------------------------------------
# 10. Agreement acceptance (electronic signature)
# ---------------------------------------------------------------------------

class AgreementAcceptance(models.Model):
    agreement = models.ForeignKey(
        Agreement, on_delete=models.CASCADE, related_name='acceptances')
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='agreement_acceptances')
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='agreement_acceptances')
    version = models.CharField(max_length=30, default='1.0')
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'compliance_agreement_acceptance'
        ordering = ['-accepted_at']
        constraints = [
            models.UniqueConstraint(
                fields=['agreement', 'school', 'version'],
                name='uq_agreement_acceptance_school_version'),
        ]

    def __str__(self):
        return f'{self.agreement.title} · school {self.school_id}'
