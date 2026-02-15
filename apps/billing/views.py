from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Q
from core.permissions import IsSchoolAdminOrHigher
from apps.billing.models import Invoice, Payment, Fee, StudentFeeAssignment, ClassFeeAssignment, SchoolFeeAssignment
from apps.billing.serializers import (
    InvoiceSerializer, 
    PaymentSerializer, 
    FeeSerializer, 
    StudentFeeAssignmentSerializer, 
    ClassFeeAssignmentSerializer,
    SchoolFeeAssignmentSerializer
)
from apps.academics.models import Class

User = get_user_model()


class FeeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Fee types
    """
    serializer_class = FeeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Fee.objects.all()
        return Fee.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class SchoolFeeAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for assigning fees to entire school (all students)
    """
    serializer_class = SchoolFeeAssignmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return SchoolFeeAssignment.objects.all()
        return SchoolFeeAssignment.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        # Save the school fee assignment
        school_fee_assignment = serializer.save(school=self.request.user.school)
        
        # Automatically create individual student fee assignments for all students in the school
        students = User.objects.filter(school=self.request.user.school, role='student')
        
        for student in students:
            StudentFeeAssignment.objects.get_or_create(
                student=student,
                fee=school_fee_assignment.fee,
                defaults={
                    'amount': school_fee_assignment.amount,
                    'due_date': school_fee_assignment.due_date
                }
            )
    
    @action(detail=True, methods=['post'])
    def apply_to_students(self, request, pk=None):
        """
        Manually trigger application of school fee to all students
        """
        school_fee_assignment = self.get_object()
        students = User.objects.filter(school=school_fee_assignment.school, role='student')
        
        created_count = 0
        for student in students:
            _, created = StudentFeeAssignment.objects.get_or_create(
                student=student,
                fee=school_fee_assignment.fee,
                defaults={
                    'amount': school_fee_assignment.amount,
                    'due_date': school_fee_assignment.due_date
                }
            )
            if created:
                created_count += 1
        
        return Response({
            'message': f'Fee assigned to {created_count} students',
            'total_students': students.count()
        })


class ClassFeeAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for assigning fees to entire classes
    """
    serializer_class = ClassFeeAssignmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return ClassFeeAssignment.objects.all()
        return ClassFeeAssignment.objects.filter(class_obj__school=self.request.user.school)
    
    def perform_create(self, serializer):
        # Save the class fee assignment
        class_fee_assignment = serializer.save()
        
        # Automatically create individual student fee assignments for all students in the class
        from apps.academics.models import StudentClass
        student_classes = StudentClass.objects.filter(class_obj=class_fee_assignment.class_obj)
        
        for student_class in student_classes:
            StudentFeeAssignment.objects.get_or_create(
                student=student_class.student,
                fee=class_fee_assignment.fee,
                defaults={
                    'amount': class_fee_assignment.amount,
                    'due_date': class_fee_assignment.due_date
                }
            )
    
    @action(detail=True, methods=['post'])
    def apply_to_students(self, request, pk=None):
        """
        Manually trigger application of class fee to all students in the class
        """
        class_fee_assignment = self.get_object()
        from apps.academics.models import StudentClass
        student_classes = StudentClass.objects.filter(class_obj=class_fee_assignment.class_obj)
        
        created_count = 0
        for student_class in student_classes:
            _, created = StudentFeeAssignment.objects.get_or_create(
                student=student_class.student,
                fee=class_fee_assignment.fee,
                defaults={
                    'amount': class_fee_assignment.amount,
                    'due_date': class_fee_assignment.due_date
                }
            )
            if created:
                created_count += 1
        
        return Response({
            'message': f'Fee assigned to {created_count} students',
            'total_students': student_classes.count()
        })


class StudentFeeAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for individual student fee assignments
    """
    serializer_class = StudentFeeAssignmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'super_admin':
            return StudentFeeAssignment.objects.all()
        elif user.role == 'student':
            # Students can only see their own fees
            return StudentFeeAssignment.objects.filter(student=user)
        else:
            # School admins and staff can see all fees in their school
            return StudentFeeAssignment.objects.filter(student__school=user.school)
    
    @action(detail=False, methods=['get'])
    def my_fees(self, request):
        """
        Get fees for the currently logged-in student
        """
        if request.user.role != 'student':
            return Response(
                {'error': 'This endpoint is only for students'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        fees = StudentFeeAssignment.objects.filter(student=request.user)
        serializer = self.get_serializer(fees, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """
        Mark a student fee as paid
        """
        fee_assignment = self.get_object()
        fee_assignment.paid = True
        fee_assignment.save()
        
        serializer = self.get_serializer(fee_assignment)
        return Response(serializer.data)


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing invoices
    """
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Invoice.objects.all()
        return Invoice.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing payments
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Payment.objects.all()
        return Payment.objects.filter(invoice__school=self.request.user.school)
