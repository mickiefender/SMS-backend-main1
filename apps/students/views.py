from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsStudent, IsSchoolAdminOrHigher, IsSchoolAdminOrTeacher
from apps.students.models import Grade, StudentGPA, StudentSocialClub, StudentSocialClubMember
from apps.students.serializers import GradeSerializer, StudentGPASerializer, StudentPortalSerializer, StudentSocialClubSerializer, StudentSocialClubMemberSerializer
from apps.students.tasks import send_faculty_advisor_notification
from django.contrib.auth import get_user_model

User = get_user_model()


class GradeViewSet(viewsets.ModelViewSet):
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Grade.objects.all()
        elif self.request.user.role == 'student':
            return Grade.objects.filter(student=self.request.user)
        return Grade.objects.filter(student__school=self.request.user.school)
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]


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
        percentage = (present / total * 100) if total > 0 else 0
        
        return Response({
            'total_classes': total,
            'present': present,
            'absent': attendances.filter(status='absent').count(),
            'late': attendances.filter(status='late').count(),
            'percentage': percentage,
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
