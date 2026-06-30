from apps.academics.models import StudentClass
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsTeacher, IsStudent
from apps.assignments.models import Assignment, AssignmentSubmission
from apps.assignments.serializers import AssignmentSerializer, AssignmentSubmissionSerializer
from rest_framework import serializers


class AssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = AssignmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['user'] = self.request.user
        return context
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Assignment.objects.all()
        elif self.request.user.role == 'teacher':
            return Assignment.objects.filter(teacher=self.request.user)
        elif self.request.user.role == 'student':
            student_classes = StudentClass.objects.filter(student=self.request.user)
            class_ids = [sc.class_obj.id for sc in student_classes]
            return Assignment.objects.filter(class_obj__id__in=class_ids)
        return Assignment.objects.filter(class_obj__school=self.request.user.school)
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        if self.action == 'student_assignments':
            return [IsAuthenticated(), IsStudent()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        assignment = serializer.save(teacher=self.request.user)
        # Send email notification to all students in the class
        from apps.messaging.tasks import send_assignment_email
        send_assignment_email.delay(assignment.id)
        
        # 🔔 ASSIGNMENT NOTIFICATIONS - Send in-app notifications to all students in the class
        try:
            from apps.academics.models import StudentClass as SC
            from core.notifications_api import send_student_notification
            
            # Get all students enrolled in this class
            student_classes = SC.objects.filter(
                class_obj=assignment.class_obj,
                is_active=True
            ).select_related('student')
            
            for sc in student_classes:
                try:
                    student = sc.student
                    if student and student.role == 'student':
                        send_student_notification(
                            student=student,
                            notification_type='assignment',
                            title='New Assignment',
                            message=f'New assignment "{assignment.title}" has been posted. Due: {assignment.due_date}',
                            related_object_id=assignment.id,
                            related_object_type='Assignment',
                            priority='normal'
                        )
                except Exception as e:
                    print(f"[Notification] Error sending to student: {e}")
        except Exception as e:
            print(f"[Notification] Error in assignment notification: {e}")

    @action(detail=False, methods=['get'], url_path='student-assignments')
    def student_assignments(self, request):
        """
        Returns a list of assignments for the classes the currently logged-in student is enrolled in.
        """
        student = request.user
        student_classes = StudentClass.objects.filter(student=student)
        class_ids = [sc.class_obj.id for sc in student_classes]
        assignments = Assignment.objects.filter(class_obj__id__in=class_ids)
        serializer = self.get_serializer(assignments, many=True)
        return Response(serializer.data)


class AssignmentSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = AssignmentSubmissionSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), IsStudent()]
        if self.action == 'grade':
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'super_admin':
            return AssignmentSubmission.objects.all()
        elif user.role == 'student':
            return AssignmentSubmission.objects.filter(student=user)
        elif user.role == 'teacher':
            return AssignmentSubmission.objects.filter(assignment__teacher=user)
        return AssignmentSubmission.objects.filter(assignment__class_obj__school=user.school)

    def perform_create(self, serializer):
        print(f"[DEBUG] perform_create called - validated_data: {serializer.validated_data}")
        print(f"[DEBUG] Request user: {self.request.user.id} - {self.request.user.role}")
        
        # Check for existing submission to prevent duplicates
        existing = AssignmentSubmission.objects.filter(
            assignment=serializer.validated_data['assignment'],
            student=self.request.user
        )
        print(f"[DEBUG] Existing submissions check: {existing.exists()}")
        if existing.exists():
            raise serializers.ValidationError(
                {"detail": "You have already submitted this assignment. Only one submission per assignment is allowed."}
            )
        submission = serializer.save(student=self.request.user, status='submitted')
        print(f"[DEBUG] Submission created with ID: {submission.id}")

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsTeacher])
    def grade(self, request, pk=None):
        """Grade a submission"""
        submission = self.get_object()
        
        # Store old score for notification comparison
        old_score = submission.score
        new_score = request.data.get('score')
        
        submission.score = new_score
        submission.feedback = request.data.get('feedback', '')
        submission.status = 'graded'
        submission.graded_at = timezone.now()
        submission.save()
        
        # 🔔 GRADED SUBMISSION NOTIFICATIONS - Send notification when assignment is graded
        try:
            from core.notifications_api import send_student_notification
            
            score_msg = f"Score: {new_score}/{submission.assignment.max_score}"
            if old_score != new_score:
                send_student_notification(
                    student=submission.student,
                    notification_type='grading',
                    title='Assignment Graded',
                    message=f'Your submission for "{submission.assignment.title}" has been graded. {score_msg}',
                    related_object_id=submission.id,
                    related_object_type='AssignmentSubmission',
                    priority='normal'
                )
        except Exception as e:
            print(f"[Notification] Error sending graded notification: {e}")
        
        return Response(self.get_serializer(submission).data)
