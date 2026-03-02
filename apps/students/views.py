from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from core.permissions import IsStudent, IsSchoolAdminOrHigher, IsSchoolAdminOrTeacher
from apps.students.models import Grade, StudentGPA, StudentSocialClub, StudentSocialClubMember
from apps.students.serializers import GradeSerializer, StudentGPASerializer, StudentPortalSerializer, StudentSocialClubSerializer, StudentSocialClubMemberSerializer
from apps.students.tasks import send_faculty_advisor_notification
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class GradeViewSet(viewsets.ModelViewSet):
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated]
    
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
            class_subject_teacher_ids = ClassSubjectTeacher.objects.filter(
                teacher=user, is_active=True
            ).values_list('class_obj_id', 'subject_id')
            
            print(f"[GradeViewSet] Teacher class_subject_teacher_ids: {list(class_subject_teacher_ids)}")
            
            # Build base queryset - include grades the teacher created
            queryset = Grade.objects.filter(
                Q(student__school=user.school) | Q(locked_by=user)
            ).select_related('student', 'subject')
            
            if class_subject_teacher_ids:
                # Get students in those classes
                student_ids = StudentClass.objects.filter(
                    class_obj_id__in=[cst[0] for cst in class_subject_teacher_ids],
                    is_active=True
                ).values_list('student_id', flat=True).distinct()
                
                print(f"[GradeViewSet] Teacher student_ids: {list(student_ids)}")
                
                # Get subjects they teach
                subject_ids = [cst[1] for cst in class_subject_teacher_ids]
                print(f"[GradeViewSet] Teacher subject_ids: {subject_ids}")
                
                # Filter grades by these students and subjects
                queryset = queryset.filter(
                    Q(student_id__in=student_ids) | Q(subject_id__in=subject_ids) | Q(locked_by=user)
                )
            
            return queryset.distinct()
        
        # School admins see all grades in their school
        return Grade.objects.filter(student__school=user.school).select_related('student', 'subject')
    
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
                serializer.save(academic_session=current_session)
            else:
                serializer.save()
        else:
            serializer.save()
    
    def perform_update(self, serializer):
        """Prevent updating locked grades"""
        grade = self.get_object()
        if grade.is_locked:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": "Cannot update a locked grade. Please unlock first."})
        serializer.save()
    
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


class StudentPortalViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsStudent]
    
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
        """Get all billing for a student"""
        from apps.billing.models import Billing
        from apps.billing.serializers import BillingSerializer
        
        billing = Billing.objects.filter(student=request.user)
        return Response(BillingSerializer(billing, many=True).data)


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
