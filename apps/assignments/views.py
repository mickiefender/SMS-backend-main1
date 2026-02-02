from apps.academics.models import StudentClass
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsTeacher, IsStudent
from apps.assignments.models import Assignment, AssignmentSubmission
from apps.assignments.serializers import AssignmentSerializer, AssignmentSubmissionSerializer


class AssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = AssignmentSerializer
    permission_classes = [IsAuthenticated]
    
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
        serializer.save(teacher=self.request.user)

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
        serializer.save(student=self.request.user, status='submitted')

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsTeacher])
    def grade(self, request, pk=None):
        """Grade a submission"""
        submission = self.get_object()
        submission.score = request.data.get('score')
        submission.feedback = request.data.get('feedback', '')
        submission.status = 'graded'
        submission.graded_at = timezone.now()
        submission.save()
        return Response(self.get_serializer(submission).data)
