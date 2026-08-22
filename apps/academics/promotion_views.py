"""
Student Promotion REST APIs.

All endpoints are tenant-scoped: school admins only ever see/modify data
belonging to their own school (queryset-level filtering, not client-side).
"""
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from core.permissions import CanManageStudents, IsSchoolAdminOrHigher
from apps.academics.models import (
    AcademicYear,
    Class,
    PromotionBatch,
    PromotionPolicy,
    PromotionRecord,
    PromotionRule,
)
from apps.academics.promotion_service import (
    auto_decisions_from_preview,
    build_promotion_preview,
    execute_promotions,
    get_school_filter,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

class AcademicYearSerializer(serializers.ModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AcademicYear
        fields = ['id', 'school', 'name', 'start_date', 'end_date',
                  'is_current', 'status', 'created_at', 'updated_at']
        read_only_fields = ['school', 'created_at', 'updated_at']

    def validate(self, data):
        start = data.get('start_date') or (self.instance.start_date if self.instance else None)
        end = data.get('end_date') or (self.instance.end_date if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError('end_date must be after start_date')
        return data


class PromotionRuleSerializer(serializers.ModelSerializer):
    from_class_name = serializers.CharField(source='from_class.name', read_only=True)
    to_class_name = serializers.CharField(source='to_class.name', read_only=True)

    class Meta:
        model = PromotionRule
        fields = ['id', 'school', 'from_class', 'from_class_name', 'to_class',
                  'to_class_name', 'order', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['school', 'created_at', 'updated_at']


class PromotionPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionPolicy
        fields = ['id', 'school', 'mode', 'pass_mark', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['school', 'created_at', 'updated_at']


class PromotionRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_number = serializers.SerializerMethodField()
    from_class_name = serializers.CharField(source='from_class.name', read_only=True)
    to_class_name = serializers.CharField(source='to_class.name', read_only=True)

    class Meta:
        model = PromotionRecord
        fields = ['id', 'student', 'student_name', 'student_number', 'action',
                  'from_class', 'from_class_name', 'to_class', 'to_class_name',
                  'final_average', 'reason', 'warning', 'status', 'error_message',
                  'created_at']

    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    def get_student_number(self, obj):
        profile = getattr(obj.student, 'student_profile', None)
        return getattr(profile, 'student_id', '')


class PromotionBatchSerializer(serializers.ModelSerializer):
    source_year_name = serializers.CharField(source='source_academic_year.name', read_only=True)
    destination_year_name = serializers.CharField(source='destination_academic_year.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PromotionBatch
        fields = ['id', 'source_academic_year', 'source_year_name',
                  'destination_academic_year', 'destination_year_name',
                  'created_by', 'created_by_name', 'total_students',
                  'promoted_count', 'repeated_count', 'graduated_count',
                  'withdrawn_count', 'transferred_count', 'failed_count',
                  'skipped_count', 'status', 'created_at', 'completed_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


class PromotionDecisionSerializer(serializers.Serializer):
    """One per-student decision inside a bulk promotion request."""
    student_id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=['promote', 'repeat', 'graduate',
                                              'withdraw', 'transfer'])
    to_class_id = serializers.IntegerField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# ViewSets (CRUD for configuration + history)
# ---------------------------------------------------------------------------

from rest_framework import viewsets


class AcademicYearViewSet(viewsets.ModelViewSet):
    serializer_class = AcademicYearSerializer
    queryset = AcademicYear.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        qs = self.queryset.select_related('school')
        if school_id is None:
            return qs.all()
        return qs.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if not school_id:
            raise serializers.ValidationError('Super admins must specify a school context.')
        with transaction.atomic():
            instance = serializer.save(school_id=school_id)
            # Marking a year current completes the previous active year.
            if instance.is_current:
                AcademicYear.objects.filter(
                    school_id=school_id, status='active'
                ).exclude(id=instance.id).update(status='completed')


class PromotionRuleViewSet(viewsets.ModelViewSet):
    serializer_class = PromotionRuleSerializer
    queryset = PromotionRule.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), CanManageStudents()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        qs = self.queryset.select_related('from_class', 'to_class', 'school')
        if school_id is None:
            return qs.all()
        return qs.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if not school_id:
            raise serializers.ValidationError('Super admins must specify a school context.')
        serializer.save(school_id=school_id)


class PromotionPolicyViewSet(viewsets.ModelViewSet):
    serializer_class = PromotionPolicySerializer
    queryset = PromotionPolicy.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), CanManageStudents()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if not school_id:
            raise serializers.ValidationError('Super admins must specify a school context.')
        serializer.save(school_id=school_id)


class PromotionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    """Promotion history — list batches / open one batch with its records."""
    queryset = PromotionBatch.objects.all()

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PromotionBatchSerializer  # records added in retrieve()
        return PromotionBatchSerializer

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        qs = self.queryset.select_related(
            'source_academic_year', 'destination_academic_year', 'created_by'
        )
        if school_id is None:
            return qs.all()
        return qs.filter(school_id=school_id)

    def retrieve(self, request, *args, **kwargs):
        batch = self.get_object()
        data = PromotionBatchSerializer(batch).data
        records = batch.records.select_related(
            'student', 'from_class', 'to_class', 'student__student_profile'
        ).order_by('student__first_name', 'student__last_name')

        # Optional filters when opening a batch.
        record_status = request.query_params.get('status')
        if record_status:
            records = records.filter(status=record_status)
        action_filter = request.query_params.get('action')
        if action_filter:
            records = records.filter(action=action_filter)

        data['records'] = PromotionRecordSerializer(records, many=True).data
        return Response(data)


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------

def _resolve_years(request, data):
    """Resolve + tenant-check source/destination academic years."""
    school_id = get_school_filter(request.user)
    if not school_id:
        return None, None, Response(
            {'error': 'No school access'}, status=status.HTTP_403_FORBIDDEN)

    try:
        source_year = AcademicYear.objects.get(
            id=data.get('source_academic_year'), school_id=school_id)
        dest_year = AcademicYear.objects.get(
            id=data.get('destination_academic_year'), school_id=school_id)
    except AcademicYear.DoesNotExist:
        return None, None, Response(
            {'error': 'Academic year not found in your school'},
            status=status.HTTP_404_NOT_FOUND)

    if source_year.id == dest_year.id:
        return None, None, Response(
            {'error': 'Source and destination academic years must differ'},
            status=status.HTTP_400_BAD_REQUEST)

    return (source_year, dest_year), school_id, None


class PromotionPreviewView(APIView):
    """
    GET/POST /api/academics/promotion/preview/
    Body/query: source_academic_year, destination_academic_year, class_ids?[]
    Read-only — never modifies enrollment state.
    """
    permission_classes = [IsAuthenticated]

    def _preview(self, request, data):
        resolved, school_id, error = _resolve_years(request, data)
        if error:
            return error
        source_year, dest_year = resolved

        class_ids = data.get('class_ids') or None
        preview = build_promotion_preview(school_id, source_year, dest_year, class_ids)
        return Response(preview)

    def get(self, request):
        params = {
            'source_academic_year': request.query_params.get('source_academic_year'),
            'destination_academic_year': request.query_params.get('destination_academic_year'),
        }
        class_ids = request.query_params.getlist('class_ids')
        if class_ids:
            params['class_ids'] = [c for c in class_ids if str(c).isdigit()]
        return self._preview(request, params)

    def post(self, request):
        return self._preview(request, request.data or {})


class PromotionBulkView(APIView):
    """
    POST /api/academics/promotion/bulk/

    Body:
      {
        "source_academic_year": 12,
        "destination_academic_year": 13,
        "decisions": [{"student_id": 1, "action": "promote", "to_class_id": 5}, ...]
      }

    OR omit "decisions" to execute every recommended action from the preview
    (manual_review students are excluded automatically).

    Runs in ONE atomic transaction; idempotent on re-submission.
    """
    permission_classes = [IsAuthenticated, CanManageStudents]

    def post(self, request):
        data = request.data or {}
        resolved, school_id, error = _resolve_years(request, data)
        if error:
            return error
        source_year, dest_year = resolved

        decisions = data.get('decisions')
        if not decisions:
            preview = build_promotion_preview(school_id, source_year, dest_year)
            decisions = auto_decisions_from_preview(preview)

        if not decisions:
            return Response({'error': 'No students to promote'}, status=400)

        batch = execute_promotions(school_id, request.user, source_year, dest_year, decisions)
        return Response(PromotionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class StudentPromoteView(APIView):
    """
    POST /api/academics/students/{id}/promote/
    Body: {from_academic_year, to_academic_year?, to_class?, action}
    Validates the student belongs to the caller's school and has an active
    enrollment in the source academic year.
    """
    permission_classes = [IsAuthenticated, CanManageStudents]

    def post(self, request, student_id):
        school_id = get_school_filter(request.user)
        if not school_id:
            return Response({'error': 'No school access'}, status=status.HTTP_403_FORBIDDEN)

        # Tenant isolation: the student MUST belong to the caller's school.
        student = get_object_or_404(User, id=student_id, school_id=school_id, role='student')

        data = request.data or {}
        action = str(data.get('action', 'promote')).lower()
        if action not in {'promote', 'repeat', 'graduate', 'withdraw', 'transfer'}:
            return Response({'error': f'Invalid action: {action}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            source_year = AcademicYear.objects.get(
                id=data.get('from_academic_year'), school_id=school_id)
        except AcademicYear.DoesNotExist:
            return Response({'error': 'Source academic year not found in your school'},
                            status=status.HTTP_404_NOT_FOUND)

        dest_year = None
        if data.get('to_academic_year'):
            try:
                dest_year = AcademicYear.objects.get(
                    id=data.get('to_academic_year'), school_id=school_id)
            except AcademicYear.DoesNotExist:
                return Response({'error': 'Destination academic year not found in your school'},
                                status=status.HTTP_404_NOT_FOUND)

        if action in ('promote', 'repeat'):
            if not dest_year:
                return Response({'error': 'to_academic_year is required for promote/repeat'},
                                status=status.HTTP_400_BAD_REQUEST)
            if dest_year.id == source_year.id:
                return Response({'error': 'Destination year must differ from source year'},
                                status=status.HTTP_400_BAD_REQUEST)

        # Validate the student actually has an enrollment in the source year.
        from apps.academics.models import StudentEnrollment
        enrollment = StudentEnrollment.objects.filter(
            student=student, academic_year=source_year, school_id=school_id).first()
        if not enrollment:
            return Response(
                {'error': f'Student has no enrollment in {source_year.name}'},
                status=status.HTTP_400_BAD_REQUEST)

        override_class_id = data.get('to_class')
        if override_class_id:
            cls = Class.objects.filter(id=override_class_id, school_id=school_id).first()
            if not cls:
                return Response({'error': 'Destination class not found in your school'},
                                status=status.HTTP_403_FORBIDDEN)

        batch = execute_promotions(
            school_id, request.user, source_year, dest_year,
            [{'student_id': student.id, 'action': action, 'to_class_id': override_class_id}],
        )
        return Response(PromotionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class StudentAcademicHistoryView(APIView):
    """
    GET /api/academics/students/{id}/academic-history/
    Permanent, append-only history of the student's enrollments per academic
    year plus their promotion records. Historical rows are never modified.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        school_id = get_school_filter(request.user)
        if not school_id:
            return Response({'error': 'No school access'}, status=status.HTTP_403_FORBIDDEN)

        student = get_object_or_404(User, id=student_id, school_id=school_id, role='student')

        from apps.academics.models import StudentEnrollment
        enrollments = (
            StudentEnrollment.objects.filter(student=student, school_id=school_id)
            .select_related('academic_year', 'class_obj', 'promoted_from')
            .order_by('academic_year__start_date')
        )

        history = [{
            'enrollment_id': e.id,
            'academic_year_id': e.academic_year_id,
            'academic_year': e.academic_year.name,
            'year_status': e.academic_year.status,
            'class_id': e.class_obj_id,
            'class_name': e.class_obj.name,
            'status': e.status,
            'notes': e.notes,
            'created_at': e.created_at,
        } for e in enrollments]

        promotions = (
            PromotionRecord.objects.filter(student=student, batch__school_id=school_id)
            .select_related('batch', 'batch__source_academic_year',
                            'batch__destination_academic_year', 'from_class', 'to_class')
            .order_by('-created_at')
        )
        promotion_history = [{
            'id': p.id,
            'batch_id': p.batch_id,
            'from_year': p.batch.source_academic_year.name,
            'to_year': p.batch.destination_academic_year.name,
            'action': p.action,
            'from_class': p.from_class.name if p.from_class else None,
            'to_class': p.to_class.name if p.to_class else None,
            'final_average': p.final_average,
            'reason': p.reason,
            'status': p.status,
            'date': p.created_at,
        } for p in promotions]

        return Response({
            'student_id': student.id,
            'student_name': student.get_full_name() or student.username,
            'history': history,
            'promotions': promotion_history,
        })
