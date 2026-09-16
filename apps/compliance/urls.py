from django.urls import path
from .views import (
    ComplianceAdminQueueView,
    ComplianceDocumentsView,
    ComplianceDocumentUploadView,
    ComplianceProfileView,
    ComplianceStatusView,
    ComplianceAdminReviewView,
    ComplianceAdminApproveAccountView,
    AgreementView,
    AgreementDecisionView,
)

urlpatterns = [
    path('status/', ComplianceStatusView.as_view(), name='compliance-status'),
    path('profile/', ComplianceProfileView.as_view(), name='compliance-profile'),
    path('documents/upload/', ComplianceDocumentUploadView.as_view(), name='compliance-document-upload'),
    path('admin/queue/', ComplianceAdminQueueView.as_view(), name='compliance-admin-queue'),
    path('admin/documents/', ComplianceDocumentsView.as_view(), name='compliance-admin-documents'),
    path('admin/review/<int:school_id>/', ComplianceAdminReviewView.as_view(), name='compliance-admin-review'),
    path('admin/approve-account/<int:school_id>/', ComplianceAdminApproveAccountView.as_view(), name='compliance-admin-approve-account'),
    path('agreement/', AgreementView.as_view(), name='compliance-agreement'),
    path('agreement/decision/', AgreementDecisionView.as_view(), name='compliance-agreement-decision'),
]
