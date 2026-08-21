from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from core.permissions import IsStudent, IsSchoolAdminOrHigher, IsSchoolAdminOrTeacher
from apps.students.models import Grade, StudentGPA, StudentSocialClub, StudentSocialClubMember
from apps.students.serializers import GradeSerializer, StudentGPASerializer, StudentPortalSerializer, StudentSocialClubSerializer, StudentSocialClubMemberSerializer
from apps.students.tasks import send_faculty_advisor_notification
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.notifications import notification_service

User = get_user_model()


class LargePagePagination(PageNumberPagination):
    """
    Pagination that lets clients request a larger page via ?page_size=N.
    Bounded so no client can blow up the server: max 500 rows per page.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 500


class GradeViewSet(viewsets.ModelViewSet):
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargePagePagination
    filterset_fields = ['student', 'subject', 'assessment_type', 'academic_session']
    
    def get_queryset(self):
        user = self.request.user
        print(f"[GradeViewSet] get_queryset for user: {user}, role: {user.role}")
        
        if user.role == 'super_admin':
            return Grade.objects.all().select_related('student', 'subject')
        elif user.role == 'student':
            return Grade.objects.filter(student=user).select_related('student', 'subject')
        elif user.role == 'teacher':
            # Teachers can see grades they created OR grades for their assigned classes/subjects
            from apps.academics.models import ClassSubjectTeacher, StudentClass
            
            # Get class subject teachers for this teacher
            class_subject_teacher_ids = list(
                ClassSubjectTeacher.objects.filter(
                    teacher=user, is_active=True
                ).values_list('class_obj_id', 'subject_id')
            )
            
            print(f"[GradeViewSet] Teacher class_subject_teacher_ids: {class_subject_teacher_ids}")
            
            # Build base queryset - include grades in teacher school + grades explicitly locked by teacher
            queryset = Grade.objects.filter(
                Q(student__school=user.school) | Q(locked_by=user)
            ).select_related('student', 'subject', 'academic_session')
            
            if class_subject_teacher_ids:
                # Get students in those classes
                class_ids = [cst[0] for cst in class_subject_teacher_ids]
                subject_ids = [cst[1] for cst in class_subject_teacher_ids]

                student_ids = StudentClass.objects.filter(
                    class_obj_id__in=class_ids,
                    is_active=True
                ).values_list('student_id', flat=True).distinct()
                
                print(f"[GradeViewSet] Teacher student_ids: {list(student_ids)}")
                print(f"[GradeViewSet] Teacher subject_ids: {subject_ids}")
                
                # Teacher sees grades only when BOTH student and subject are in teacher assignment scope
                queryset = queryset.filter(
                    (Q(student_id__in=student_ids) & Q(subject_id__in=subject_ids)) | Q(locked_by=user)
                )
            else:
                # No assignment: teacher can only see grades they explicitly locked
                queryset = queryset.filter(Q(locked_by=user))
            
            return queryset.distinct()
        
        # School admins see all grades in their school
        queryset = Grade.objects.filter(student__school=user.school).select_related('student', 'subject', 'academic_session')

        # Optional class scoping: ?class_obj=<id> returns only grades of
        # students actively assigned to that class. Used by the Examination
        # score-entry grid to load a whole class in one request.
        class_id = self.request.query_params.get('class_obj')
        if class_id:
            queryset = queryset.filter(
                student__class_assignments__class_obj_id=class_id,
                student__class_assignments__is_active=True,
            ).distinct()

        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create a new grade"""
        print(f"[GradeViewSet] create called with request.data: {request.data}")
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print(f"[GradeViewSet] create error: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        """Set academic session if not provided"""
        print(f"[GradeViewSet] perform_create called with data: {serializer.validated_data}")
        academic_session = serializer.validated_data.get('academic_session')
        if not academic_session:
            # Try to get current session
            from apps.academics.models import AcademicSession
            student = serializer.validated_data.get('student')
            print(f"[GradeViewSet] Student: {student}, School: {student.school if student else 'None'}")
            current_session = AcademicSession.objects.filter(
                school=student.school if student else None,
                is_current=True
            ).first()
            print(f"[GradeViewSet] Current session found: {current_session}")
            if current_session:
                grade = serializer.save(academic_session=current_session)
            else:
                grade = serializer.save()
        else:
            grade = serializer.save()

        try:
            student = grade.student
            subject_name = getattr(grade.subject, 'name', 'Subject')
            score = getattr(grade, 'score', '')
            notification_service.send_notification(
                user_id=student.id,
                notification_type='grading',
                title='Grade Posted',
                message=f'Your grade for {subject_name} has been posted: {score}.',
                data={'grade_id': grade.id, 'subject_name': subject_name, 'score': str(score)},
                priority='normal'
            )
        except Exception as notify_error:
            print(f"[GradeViewSet] Failed to send grade notification: {notify_error}")
    
    def perform_update(self, serializer):
        """Prevent updating locked grades"""
        grade = self.get_object()
        if grade.is_locked:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": "Cannot update a locked grade. Please unlock first."})
        updated_grade = serializer.save()

        try:
            student = updated_grade.student
            subject_name = getattr(updated_grade.subject, 'name', 'Subject')
            score = getattr(updated_grade, 'score', '')
            notification_service.send_notification(
                user_id=student.id,
                notification_type='grading',
                title='Grade Updated',
                message=f'Your grade for {subject_name} has been updated to {score}.',
                data={'grade_id': updated_grade.id, 'subject_name': subject_name, 'score': str(score)},
                priority='normal'
            )
        except Exception as notify_error:
            print(f"[GradeViewSet] Failed to send grade update notification: {notify_error}")
    
    def perform_destroy(self, instance):
        """Prevent deleting locked grades"""
        if instance.is_locked:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": "Cannot delete a locked grade. Please unlock first."})
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """Lock a grade to prevent further editing"""
        grade = self.get_object()
        
        if grade.is_locked:
            return Response({'error': 'Grade is already locked'}, status=400)
        
        grade.is_locked = True
        grade.locked_by = request.user
        grade.locked_at = timezone.now()
        grade.save()
        
        return Response({
            'success': True,
            'message': 'Grade locked successfully',
            'grade_id': grade.id,
            'locked_at': grade.locked_at
        })
    
    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """Unlock a grade to allow editing"""
        grade = self.get_object()
        
        if not grade.is_locked:
            return Response({'error': 'Grade is not locked'}, status=400)
        
        grade.is_locked = False
        grade.locked_by = None
        grade.locked_at = None
        grade.save()
        
        return Response({
            'success': True,
            'message': 'Grade unlocked successfully',
            'grade_id': grade.id
        })
    
    @action(detail=False, methods=['post'])
    def lock_by_class(self, request):
        """Lock all grades for a class and subject"""
        class_id = request.data.get('class_id')
        subject_id = request.data.get('subject_id')
        academic_session_id = request.data.get('academic_session_id')
        
        if not class_id or not subject_id:
            return Response({'error': 'class_id and subject_id are required'}, status=400)
        
        from apps.academics.models import StudentClass
        from apps.students.models import Grade
        
        # Get student IDs in this class
        student_ids = StudentClass.objects.filter(
            class_obj_id=class_id,
            is_active=True
        ).values_list('student_id', flat=True)
        
        # Build query
        query = Grade.objects.filter(
            student_id__in=student_ids,
            subject_id=subject_id,
            is_locked=False
        )
        
        if academic_session_id:
            query = query.filter(academic_session_id=academic_session_id)
        
        # Lock all grades
        updated_count = query.update(
            is_locked=True,
            locked_by=request.user,
            locked_at=timezone.now()
        )
        
        return Response({
            'success': True,
            'message': f'{updated_count} grades locked successfully'
        })
    
    @action(detail=False, methods=['post'])
    def unlock_by_class(self, request):
        """Unlock all grades for a class and subject"""
        class_id = request.data.get('class_id')
        subject_id = request.data.get('subject_id')
        academic_session_id = request.data.get('academic_session_id')
        
        if not class_id or not subject_id:
            return Response({'error': 'class_id and subject_id are required'}, status=400)
        
        from apps.academics.models import StudentClass
        from apps.students.models import Grade
        
        # Get student IDs in this class
        student_ids = StudentClass.objects.filter(
            class_obj_id=class_id,
            is_active=True
        ).values_list('student_id', flat=True)
        
        # Build query
        query = Grade.objects.filter(
            student_id__in=student_ids,
            subject_id=subject_id,
            is_locked=True
        )
        
        if academic_session_id:
            query = query.filter(academic_session_id=academic_session_id)
        
        # Unlock all grades
        updated_count = query.update(
            is_locked=False,
            locked_by=None,
            locked_at=None
        )
        
        return Response({
            'success': True,
            'message': f'{updated_count} grades unlocked successfully'
        })

    @action(detail=False, methods=['get'])
    def grade_entry_data(self, request):
        """
        Return full class students list and teacher-allowed subjects for grade entry.
        Query params:
          - class_id (required)
        """
        user = request.user
        class_id = request.query_params.get('class_id')

        if user.role != 'teacher':
            return Response({'error': 'Only teachers can access this endpoint.'}, status=403)

        if not class_id:
            return Response({'error': 'class_id is required'}, status=400)

        from apps.academics.models import StudentClass, ClassSubjectTeacher

        from apps.academics.models import ClassSubjectTeacher, ClassTeacher, ClassSubject, StudentClass
        
        # Check if teacher teaches subjects in this class OR is form tutor
        teacher_subject_qs = ClassSubjectTeacher.objects.filter(
            teacher=user,
            class_obj_id=class_id,
            is_active=True
        ).select_related('subject')
        
        is_form_tutor = False
        if not teacher_subject_qs.exists():
            # Fallback: Check if teacher is form tutor for this class
            form_tutor_qs = ClassTeacher.objects.filter(
                teacher=user,
                class_obj_id=class_id,
                is_form_tutor=True
            )
            is_form_tutor = form_tutor_qs.exists()
            
            if not is_form_tutor:
                return Response(
                    {'error': f"No subjects assigned to class {class_id}. Ensure ClassSubject records exist, or assign teacher as form tutor."},
                    status=403
                )
        
        # Full active student list in selected class
        student_classes = StudentClass.objects.filter(
            class_obj_id=class_id,
            is_active=True
        ).select_related('student').order_by('student__first_name', 'student__last_name')

        students = []
        for sc in student_classes:
            student = sc.student
            students.append({
                'id': student.id,
                'first_name': student.first_name,
                'last_name': student.last_name,
                'full_name': student.get_full_name(),
                'email': student.email,
            })

        # Subjects: Specific ones if subject teacher, ALL class subjects if form tutor
        subjects = []
        seen_subject_ids = set()
        
        if teacher_subject_qs.exists():
            # Subject teacher: only their subjects
            for cst in teacher_subject_qs:
                if cst.subject_id in seen_subject_ids:
                    continue
                seen_subject_ids.add(cst.subject_id)
                subjects.append({
                    'id': cst.subject.id,
                    'name': cst.subject.name,
                    'code': getattr(cst.subject, 'code', None),
                })
        else:
            # Form tutor: all subjects assigned to class
            class_subjects = ClassSubject.objects.filter(
                class_obj_id=class_id
            ).select_related('subject').distinct('subject')
            for cs in class_subjects:
                subjects.append({
                    'id': cs.subject.id,
                    'name': cs.subject.name,
                    'code': getattr(cs.subject, 'code', None),
                })
        
        print(f"[grade_entry_data] Teacher {user.id}: {len(subjects)} subjects, {len(students)} students, form_tutor={is_form_tutor}")

        return Response({
            'class_id': int(class_id),
            'students': students,
            'subjects': subjects,
            'is_form_tutor': is_form_tutor  # Frontend hint
        })


    @action(detail=False, methods=['post'])
    def validate_grade_access(self, request):
        """
        Preview validation for grade submission - tells frontend if POST will succeed.
        Body: {student_id: int, subject_id: int, class_id?: int}
        """
        if request.user.role != 'teacher':
            return Response({'valid': False, 'reason': 'Only teachers can validate grade access.'}, status=403)

        student_id = request.data.get('student_id')
        subject_id = request.data.get('subject_id')

        if not student_id or not subject_id:
            return Response({
                'valid': False, 
                'reason': 'student_id and subject_id required.'
            }, status=400)

        from apps.academics.models import StudentClass, ClassSubjectTeacher, ClassTeacher
        from apps.students.models import Grade
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            student = User.objects.get(id=student_id, role='student')
            subject = Subject.objects.get(id=subject_id)
        except (User.DoesNotExist, Subject.DoesNotExist):
            return Response({'valid': False, 'reason': 'Invalid student or subject.'})

        # Exact same logic as GradeSerializer.validate()
        student_class_ids = list(StudentClass.objects.filter(
            student=student, is_active=True
        ).values_list('class_obj_id', flat=True))

        # Direct subject assignment
        subject_assigned = ClassSubjectTeacher.objects.filter(
            teacher=request.user,
            subject=subject,
            class_obj_id__in=student_class_ids,
            is_active=True
        ).exists()

        valid = False
        reason = "Not assigned"

        if subject_assigned:
            valid = True
            reason = "Direct subject assignment ✓"
        else:
            # Fallback: form tutor
            form_tutor = ClassTeacher.objects.filter(
                teacher=request.user,
                class_obj_id__in=student_class_ids,
                is_form_tutor=True
            ).exists()
            if form_tutor:
                valid = True
                reason = "Form tutor fallback ✓"

        # Data for frontend
        active_classes = list(StudentClass.objects.filter(
            student=student, is_active=True
        ).select_related('class_obj').values_list('class_obj__name', flat=True))

        teacher_assignments = list(ClassSubjectTeacher.objects.filter(
            teacher=request.user, is_active=True
        ).select_related('class_obj', 'subject')[:10].values_list(
            'class_obj__name', 'subject__name'
        ))

        # Existing grade check
        existing_grade = Grade.objects.filter(
            student=student, subject=subject, created_by=request.user
        ).exists()

        return Response({
            'valid': valid,
            'reason': reason,
            'student_classes': active_classes,
            'teacher_assignments': teacher_assignments,
            'existing_grade': existing_grade,
            'debug': {
                'student_class_ids': student_class_ids,
                'user_id': request.user.id,
                'user_name': request.user.get_full_name()
            }
        })


class StudentPortalViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsStudent]
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Unified dashboard endpoint - returns student dashboard data in a single response.
        Returns: {
            'total_classes': int,
            'total_subjects': int,
            'attendance': {'presence_percentage': float},
            'pending_assignments': int,
            'total_assignments': int,
            'performance': {'overall': float},
        }
        """
        try:
            from apps.academics.models import StudentClass, ClassSubject
            from apps.attendance.models import Attendance
            from apps.assignments.models import Assignment, AssignmentSubmission
            from apps.students.models import Grade
            
            user = request.user
            
            # Get student's classes count using StudentClass model (not Enrollment)
            student_classes = StudentClass.objects.filter(student=user, is_active=True)
            total_classes = student_classes.count()
            
            # Get total subjects - unique subjects across all enrolled classes
            class_ids = student_classes.values_list('class_obj_id', flat=True).distinct()
            class_subjects = ClassSubject.objects.filter(class_obj_id__in=class_ids)
            total_subjects = class_subjects.values('subject_id').distinct().count()
            
            # Attendance percentage
            attendances = Attendance.objects.filter(student=user)
            total_days = attendances.count()
            present_days = attendances.filter(status='present').count()
            presence_percentage = (present_days / total_days * 100) if total_days > 0 else 0.0
            
            # Assignments
            assignments = Assignment.objects.filter(class_obj_id__in=class_ids)
            total_assignments = assignments.count()
            
            # Pending assignments (not submitted)
            pending_assignments = 0
            for assignment in assignments:
                submission = AssignmentSubmission.objects.filter(
                    assignment=assignment,
                    student=user
                ).first()
                if not submission or submission.status == 'not_submitted':
                    pending_assignments += 1
            
            # Performance - overall grade average
            grades = Grade.objects.filter(student=user)
            if grades.exists():
                total_score = sum(float(g.score) for g in grades if g.score is not None)
                overall = total_score / grades.count()
            else:
                overall = 0.0
            
            return Response({
                'total_classes': total_classes,
                'total_subjects': total_subjects,
                'attendance': {
                    'presence_percentage': round(presence_percentage, 2),
                },
                'pending_assignments': pending_assignments,
                'total_assignments': total_assignments,
                'performance': {
                    'overall': round(overall, 2),
                },
            })
        except Exception as e:
            print(f"[dashboard] Error: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'total_classes': 0,
                'total_subjects': 0,
                'attendance': {'presence_percentage': 0.0},
                'pending_assignments': 0,
                'total_assignments': 0,
                'performance': {'overall': 0.0},
            })
    
    @action(detail=False, methods=['get'])
    def my_portal(self, request):
        """Get student portal data"""
        serializer = StudentPortalSerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def attendance_report(self, request):
        """Get student attendance report"""
        from apps.attendance.models import Attendance
        
        attendances = Attendance.objects.filter(student=request.user)
        total = attendances.count()
        present = attendances.filter(status='present').count()
        late = attendances.filter(status='late').count()
        absent = attendances.filter(status='absent').count()
        excused = attendances.filter(status='excused').count()
        percentage = (present / total * 100) if total > 0 else 0
        
        return Response({
            'total_days': total,
            'present_days': present,
            'absent_days': absent,
            'late_days': late,
            'excused_days': excused,
            'presence_percentage': percentage,
        })
    
    @action(detail=False, methods=['get'])
    def gpa(self, request):
        """Get student GPA"""
        try:
            gpa = StudentGPA.objects.get(student=request.user)
            return Response(StudentGPASerializer(gpa).data)
        except StudentGPA.DoesNotExist:
            return Response({'error': 'GPA not found'}, status=4.04)

    @action(detail=False, methods=['get'])
    def exam_results(self, request):
        """Get exam results"""
        grades = Grade.objects.filter(student=request.user, assessment_type='exam')
        return Response(GradeSerializer(grades, many=True).data)
    
    @action(detail=False, methods=['get'])
    def assignments(self, request):
        """Get all assignments for enrolled classes"""
        try:
            from apps.academics.models import Enrollment
            from apps.assignments.models import Assignment, AssignmentSubmission
            
            print(f"[v0] Fetching assignments for user: {request.user}")
            
            # Get enrollments for student
            enrollments = Enrollment.objects.filter(student=request.user, is_active=True)
            print(f"[v0] Found {enrollments.count()} enrollments")
            
            classes = [e.class_obj for e in enrollments]
            if not classes:
                print("[v0] No classes found for student")
                return Response([])
            
            # Get assignments for those classes
            assignments = Assignment.objects.filter(class_obj__in=classes)
            print(f"[v0] Found {assignments.count()} assignments")
            
            assignment_data = []
            for assignment in assignments:
                try:
                    submission = AssignmentSubmission.objects.filter(
                        assignment=assignment,
                        student=request.user
                    ).first()
                    
                    assignment_data.append({
                        'assignment': {
                            'id': assignment.id,
                            'title': assignment.title,
                            'description': assignment.description,
                            'due_date': str(assignment.due_date) if assignment.due_date else None,
                        },
                        'submission': {
                            'status': submission.status if submission else 'not_submitted',
                            'score': submission.score if submission else None,
                            'feedback': submission.feedback if submission else None,
                        } if submission else None
                    })
                except Exception as e:
                    print(f"[v0] Error processing assignment {assignment.id}: {e}")
                    continue
            
            print(f"[v0] Returning {len(assignment_data)} assignments")
            return Response(assignment_data)
        
        except Exception as e:
            print(f"[v0] Error fetching assignments: {e}")
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=400)


class StudentBillingViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsStudent]

    @action(detail=False, methods=['get'])
    def my_billing(self, request):
        """Get all billing for a student - returns StudentFeeAssignment with payment history"""
        from apps.billing.models import StudentFeeAssignment, ManualPayment, OnlinePayment
        
        # Get all fee assignments for this student
        fee_assignments = StudentFeeAssignment.objects.filter(
            student=request.user
        ).select_related('fee').order_by('-due_date')
        
        results = []
        for fa in fee_assignments:
            # Get payment history from ManualPayment and OnlinePayment
            manual_payments = ManualPayment.objects.filter(
                fee_assignment=fa
            ).order_by('-payment_date')
            
            online_payments = OnlinePayment.objects.filter(
                fee_assignment=fa,
                status='success'
            ).order_by('-created_at')
            
            # Build payment history list
            payment_history = []
            
            for mp in manual_payments:
                payment_history.append({
                    'id': mp.id,
                    'amount': str(mp.amount),
                    'payment_date': mp.payment_date.isoformat() if mp.payment_date else None,
                    'method': mp.payment_method,
                    'reference': mp.receipt_number,
                    'note': mp.notes,
                })
            
            for op in online_payments:
                payment_history.append({
                    'id': op.id,
                    'amount': str(op.amount),
                    'payment_date': op.paid_at.isoformat() if op.paid_at else op.created_at.isoformat(),
                    'method': op.payment_method,
                    'reference': op.reference,
                    'note': op.notes,
                })
            
            # Sort payment history by date (newest first)
            payment_history.sort(key=lambda x: x['payment_date'] or '', reverse=True)
            
            # Calculate total paid from payment history
            total_paid = sum(float(p['amount']) for p in payment_history)
            
            # Build fee item response matching frontend Fee model expectations
            results.append({
                'id': fa.id,
                'student_id': fa.student_id,
                'title': fa.fee.name,
                'fee_type': fa.fee.fee_type,
                'amount': str(fa.amount),
                'total_amount': str(fa.amount),
                'amount_assigned': str(fa.amount),
                'assigned_amount': str(fa.amount),
                'paid_amount': str(fa.amount_paid),
                'amount_paid': str(fa.amount_paid),
                'total_paid': str(total_paid),
                'due_date': fa.due_date.isoformat() if fa.due_date else None,
                'due_on': fa.due_date.isoformat() if fa.due_date else None,
                'deadline': fa.due_date.isoformat() if fa.due_date else None,
                'status': fa.status,
                'payment_status': fa.status,
                'paid': fa.paid,
                'payment_history': payment_history,
                'payments': payment_history,
                'transactions': payment_history,
                'payment_records': payment_history,
                'balance': str(fa.balance),
                'fee_name': fa.fee.name,
                'description': fa.fee.description,
                'created_at': fa.created_at.isoformat() if fa.created_at else None,
                'updated_at': fa.updated_at.isoformat() if fa.updated_at else None,
                'date_created': fa.created_at.isoformat() if fa.created_at else None,
                'modified_at': fa.updated_at.isoformat() if fa.updated_at else None,
            })
        
        return Response(results)


class StudentPaymentHistoryViewSet(viewsets.ViewSet):
    """Payment history for the student dashboard."""
    permission_classes = [IsAuthenticated, IsStudent]

    @action(detail=False, methods=['get'])
    def my_payments(self, request):
        """Get all payment history for the logged-in student."""
        from apps.payments.models import Payment
        from apps.payments.serializers import StudentPaymentHistorySerializer

        payments = Payment.objects.filter(
            student=request.user,
            status='success'
        ).select_related('invoice', 'school').order_by('-created_at')

        serializer = StudentPaymentHistorySerializer(payments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_invoices(self, request):
        """Get all invoices for the logged-in student."""
        from apps.payments.models import Invoice
        from apps.payments.serializers import InvoiceSerializer

        invoices = Invoice.objects.filter(
            student=request.user
        ).prefetch_related('items').order_by('-created_at')

        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_notifications(self, request):
        """Get payment notifications for the student."""
        from apps.payments.models import Notification
        from apps.payments.serializers import NotificationSerializer

        notifications = Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:50]

        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)


class StudentNotificationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsStudent]

    @action(detail=False, methods=['get'])
    def get_notifications(self, request):
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))
        notifications = notification_service.get_user_notifications(
            user_id=request.user.id,
            limit=limit,
            offset=offset
        )
        unread_count = notification_service.get_unread_count(request.user.id)
        return Response({
            'results': notifications,
            'count': len(notifications),
            'unread_count': unread_count
        })

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        unread_count = notification_service.get_unread_count(request.user.id)
        return Response({'unread_count': unread_count})

    @action(detail=False, methods=['post'])
    def mark_read(self, request):
        notification_index = request.data.get('notification_index')
        if notification_index is None:
            return Response({'error': 'notification_index is required'}, status=400)

        success = notification_service.mark_notification_read(
            user_id=request.user.id,
            notification_index=int(notification_index)
        )
        if not success:
            return Response({'error': 'Failed to mark notification as read'}, status=500)

        return Response({
            'success': True,
            'unread_count': notification_service.get_unread_count(request.user.id)
        })

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        notifications = notification_service.get_user_notifications(
            user_id=request.user.id,
            limit=100,
            offset=0
        )
        for idx, _ in enumerate(notifications):
            notification_service.mark_notification_read(request.user.id, idx)

        return Response({
            'success': True,
            'unread_count': notification_service.get_unread_count(request.user.id)
        })


class StudentSocialClubViewSet(viewsets.ModelViewSet):
    queryset = StudentSocialClub.objects.all()
    serializer_class = StudentSocialClubSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        club = serializer.save()
        send_faculty_advisor_notification.delay(club.id)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def members(self, request, pk=None):
        """Get all members of a social club, optionally filtered by status"""
        club = self.get_object()
        status = request.query_params.get('status', None)
        members = StudentSocialClubMember.objects.filter(club=club)
        if status:
            members = members.filter(status=status)
        serializer = StudentSocialClubMemberSerializer(members, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsStudent])
    def manage_membership(self, request, pk=None):
        """Join or leave a social club"""
        club = self.get_object()
        action = request.data.get('action') # 'join' or 'leave'

        if action == 'join':
            _, created = StudentSocialClubMember.objects.get_or_create(
                club=club, 
                student=request.user,
                defaults={'status': 'pending'}
            )
            if created:
                return Response({'status': 'pending'}, status=status.HTTP_201_CREATED)
            return Response({'status': 'already a member'}, status=status.HTTP_200_OK)
        
        elif action == 'leave':
            StudentSocialClubMember.objects.filter(club=club, student=request.user).delete()
            return Response({'status': 'left'}, status=status.HTTP_204_NO_CONTENT)
        
        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsSchoolAdminOrHigher])
    def approve_membership(self, request, pk=None):
        """Approve a student's membership"""
        club = self.get_object()
        student_id = request.data.get('student_id')
        try:
            member = StudentSocialClubMember.objects.get(club=club, student_id=student_id)
            member.status = 'active'
            member.save()
            return Response({'status': 'approved'}, status=status.HTTP_200_OK)
        except StudentSocialClubMember.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
