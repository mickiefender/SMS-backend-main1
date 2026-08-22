from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import timedelta
import logging
from core.permissions import (
    IsSchoolAdminOrHigher, IsSuperAdmin,
    CanManageFees, CanCollectFees, CanManageExpenses,
)
from apps.billing.models import Invoice, Payment, Fee, StudentFeeAssignment, ClassFeeAssignment, SchoolFeeAssignment, ManualPayment, OnlinePayment, SchoolExpense
from apps.billing.serializers import (
    InvoiceSerializer, 
    PaymentSerializer, 
    FeeSerializer, 
    StudentFeeAssignmentSerializer, 
    ClassFeeAssignmentSerializer,
    SchoolFeeAssignmentSerializer,
    ManualPaymentSerializer,
    RecordManualPaymentSerializer,
    OnlinePaymentSerializer,
    RecordOnlinePaymentSerializer,
    SchoolExpenseSerializer,
    RecordSchoolExpenseSerializer
)
from apps.academics.models import Class

User = get_user_model()
logger = logging.getLogger(__name__)


class FeeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Fee types
    """
    serializer_class = FeeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageFees()]
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
            return [CanManageFees()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return SchoolFeeAssignment.objects.all()
        return SchoolFeeAssignment.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        # Save the school fee assignment
        school_fee_assignment = serializer.save(school=self.request.user.school)
        
        # Automatically create individual student fee assignments for all students in the school
        created_assignments = []
        students = User.objects.filter(school=self.request.user.school, role='student')
        
        for student in students:
            obj, created = StudentFeeAssignment.objects.get_or_create(
                student=student,
                fee=school_fee_assignment.fee,
                defaults={
                    'amount': school_fee_assignment.amount,
                    'due_date': school_fee_assignment.due_date
                }
            )
            if created:
                created_assignments.append(obj.id)
        
        # Trigger bulk email notification to all students
        if created_assignments:
            from apps.billing.tasks import send_bulk_fee_assignment_email
            send_bulk_fee_assignment_email.delay(created_assignments)
    
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
            return [CanManageFees()]
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
        created_assignments = []
        student_classes = StudentClass.objects.filter(class_obj=class_fee_assignment.class_obj)
        
        for student_class in student_classes:
            obj, created = StudentFeeAssignment.objects.get_or_create(
                student=student_class.student,
                fee=class_fee_assignment.fee,
                defaults={
                    'amount': class_fee_assignment.amount,
                    'due_date': class_fee_assignment.due_date
                }
            )
            if created:
                created_assignments.append(obj.id)
        
        # Trigger bulk email notification to all students in class
        if created_assignments:
            from apps.billing.tasks import send_bulk_fee_assignment_email
            send_bulk_fee_assignment_email.delay(created_assignments)
    
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
            return [CanManageFees()]
        return [IsAuthenticated()]
    
    def create(self, request, *args, **kwargs):
        logger.info(f"=== STUDENT FEE ASSIGNMENT CREATE ===")
        logger.info(f"Request data: {request.data}")
        logger.info(f"User: {request.user.id} - {request.user.role} - {getattr(request.user, 'school', 'No school')}")

        serializer = self.get_serializer(data=request.data)
        logger.info(f"Serializer valid: {serializer.is_valid()}")
        logger.info(f"Serializer errors: {serializer.errors}")

        if serializer.is_valid():
            # Extract resolved objects from validated_data (DRF PrimaryKeyRelatedField returns objects)
            fee_obj = serializer.validated_data['fee']
            student_obj = serializer.validated_data['student']
            fee_id = fee_obj.id
            student_id = student_obj.id
            logger.info(f"Fee ID: {fee_id}, Student ID: {student_id}")

            # Use the already-validated/resolved objects
            fee = fee_obj
            student = student_obj
            logger.info(f"Fee found: {fee.id} - {fee.name} - School: {fee.school_id}")
            logger.info(f"Student found: {student.id} - {student.get_full_name()} - Role: {student.role} - School: {getattr(student, 'school_id', 'None')}")

            # Validate schools match
            if fee.school != student.school:
                logger.error(f"SCHOOL MISMATCH - Fee school: {fee.school_id}, Student school: {getattr(student, 'school_id', 'None')}")
                return Response(
                    {'error': f'Fee and student must belong to the same school. Fee: {fee.school_id}, Student: {getattr(student, "school_id", "None")}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate student role
            if student.role != 'student':
                logger.error(f"INVALID STUDENT ROLE: {student.role}")
                return Response(
                    {'error': f'Student must have role "student", got "{student.role}"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate fee active
            if not fee.is_active:
                logger.error(f"INACTIVE FEE: {fee.is_active}")
                return Response(
                    {'error': 'Fee must be active'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate school admin permission for this school
            if request.user.school != student.school:
                logger.error(f"UNAUTHORIZED SCHOOL - User school: {getattr(request.user, 'school_id', 'None')}, Student school: {getattr(student, 'school_id', 'None')}")
                return Response(
                    {'error': f'Not authorized for this school. User school: {getattr(request.user, "school_id", "None")}, Target school: {getattr(student, "school_id", "None")}'},
status=status.HTTP_403_FORBIDDEN
                )
            
            logger.info("All validations passed - attempting get_or_create...")
            
            # Use get_or_create to handle existing assignments gracefully (like bulk assignments)
            instance, created = StudentFeeAssignment.objects.get_or_create(
                student=student,
                fee=fee,
                defaults={
                    'amount': serializer.validated_data['amount'],
                    'due_date': serializer.validated_data['due_date'],
                }
            )
            
            if not created:
                # Update amount and due_date if provided (idempotent update)
                update_fields = []
                instance.amount = serializer.validated_data['amount']
                update_fields.append('amount')
                instance.due_date = serializer.validated_data['due_date']
                update_fields.append('due_date')
                instance.save(update_fields=update_fields)
                logger.info(f"UPDATED existing assignment ID: {instance.id}")
            
            logger.info(f"SUCCESS - {'Created NEW' if created else 'Updated existing'} assignment ID: {instance.id}")
            
            # 🔔 FEE NOTIFICATIONS - Send notification when fee is assigned or updated
            if created or (not created and request.data.get('amount')):
                try:
                    from core.notifications_api import send_student_notification
                    
                    send_student_notification(
                        student=student,
                        notification_type='fee',
                        title='Fee Update',
                        message=f'New fee assigned: {fee.name}. Amount: {serializer.validated_data.get("amount", fee.amount)}',
                        related_object_id=instance.id,
                        related_object_type='StudentFeeAssignment',
                        priority='normal'
                    )
                except Exception as e:
                    logger.error(f"[Notification] Error sending fee notification: {e}")
            
            # Serialize fresh instance
            serializer = self.get_serializer(instance)
            status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
            return Response(serializer.data, status=status_code)
        else:
            logger.error(f"SERIALIZER ERRORS: {serializer.errors}")
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def get_queryset(self):
        user = self.request.user
        
        # Check if a specific student is being requested via query parameter
        student_id = self.request.query_params.get('student')
        
        # Base queryset based on user role
        if user.role == 'super_admin':
            queryset = StudentFeeAssignment.objects.all()
        elif user.role == 'student':
            # Students can only see their own fees
            queryset = StudentFeeAssignment.objects.filter(student=user)
        else:
            # School admins and staff can see all fees in their school
            queryset = StudentFeeAssignment.objects.filter(student__school=user.school)
        
        # If a specific student ID is provided in the query params, filter by it
        if student_id:
            try:
                # Convert to integer to ensure proper filtering
                queryset = queryset.filter(student_id=int(student_id))
            except (ValueError, TypeError):
                # If not a valid integer, ignore the filter
                pass
        
        return queryset
    
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
            return [CanManageFees()]
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


class ManualPaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing manual payments
    """
    serializer_class = ManualPaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanCollectFees()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'super_admin':
            return ManualPayment.objects.all()
        elif user.role == 'student':
            # Students can see their own payments
            return ManualPayment.objects.filter(student=user)
        else:
            # School admins and staff can see all payments in their school
            return ManualPayment.objects.filter(school=user.school)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return RecordManualPaymentSerializer
        return ManualPaymentSerializer
    
    def perform_create(self, serializer):
        """Simplified - serializer handles creation and validation"""
        instance = serializer.save()
        # Queue email notification
        try:
            from apps.billing.tasks import send_fee_payment_email
            send_fee_payment_email.delay(instance.id)
        except Exception as e:
            logger.error(f"Failed to queue fee payment email: {e}")
    
    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """Get all payments for a specific student"""
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payments = ManualPayment.objects.filter(student_id=student_id)
        serializer = self.get_serializer(payments, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_school(self, request):
        """Get all payments for the school"""
        payments = ManualPayment.objects.filter(school=request.user.school)
        serializer = self.get_serializer(payments, many=True)
        return Response(serializer.data)


class OnlinePaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing online payments via Paystack
    """
    serializer_class = OnlinePaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'super_admin':
            return OnlinePayment.objects.all().select_related('student', 'school', 'fee_assignment', 'fee_assignment__fee')
        elif user.role == 'student':
            # Students can see their own payments
            return OnlinePayment.objects.filter(student=user).select_related('student', 'school', 'fee_assignment', 'fee_assignment__fee')
        else:
            # School admins and staff can see all payments in their school
            return OnlinePayment.objects.filter(school=user.school).select_related('student', 'school', 'fee_assignment', 'fee_assignment__fee')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return RecordOnlinePaymentSerializer
        return OnlinePaymentSerializer
    
    def create(self, request, *args, **kwargs):
        """Record a successful online payment and update the fee assignment"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get the validated data
        validated_data = serializer.validated_data
        
        # Get the student
        student_id = validated_data.get('student_id')
        try:
            student = User.objects.get(id=student_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get the school
        school = student.school
        if not school:
            return Response(
                {'error': 'Student does not belong to a school'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the fee assignment if provided
        fee_assignment = None
        fee_assignment_id = validated_data.get('fee_assignment_id')
        if fee_assignment_id:
            try:
                fee_assignment = StudentFeeAssignment.objects.get(
                    id=fee_assignment_id,
                    student=student
                )
            except StudentFeeAssignment.DoesNotExist:
                # Try to find any fee assignment for this student
                fee_assignment = None
        
        # If no specific fee assignment, try to find one that matches the fee
        if not fee_assignment:
            # Look for pending/partial fees for this student
            pending_fees = StudentFeeAssignment.objects.filter(
                student=student,
                status__in=['pending', 'partial']
            )
            if pending_fees.exists():
                fee_assignment = pending_fees.first()
        
        # Create the online payment record
        online_payment = OnlinePayment.objects.create(
            school=school,
            student=student,
            fee_assignment=fee_assignment,
            amount=validated_data['amount'],
            payment_method='paystack',
            transaction_id=validated_data.get('transaction_id', ''),
            reference=validated_data['reference'],
            status=validated_data.get('status', 'success'),
            channel=validated_data.get('channel', ''),
            notes=validated_data.get('notes', ''),
            paid_at=timezone.now() if validated_data.get('status') == 'success' else None,
        )
        
        # Update the fee assignment if found
        if fee_assignment and validated_data.get('status') == 'success':
            # Calculate new amount paid (handle None case)
            current_paid = fee_assignment.amount_paid if fee_assignment.amount_paid is not None else 0
            new_amount_paid = current_paid + validated_data['amount']
            
            # Update the fee assignment
            fee_assignment.amount_paid = new_amount_paid
            fee_assignment.save()  # This will auto-update status
            
            logger.info(f"Updated fee assignment {fee_assignment.id} - new amount_paid: {new_amount_paid}")
        
        # Send email notifications to BOTH student AND school admin
        try:
            from apps.billing.tasks import send_online_payment_email
            send_online_payment_email.delay(online_payment.id)
        except Exception as e:
            logger.error(f"Failed to queue online payment email: {e}")
        
        # Return the created payment
        output_serializer = OnlinePaymentSerializer(online_payment)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """Get all online payments for a specific student"""
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payments = OnlinePayment.objects.filter(student_id=student_id).select_related('student', 'school', 'fee_assignment', 'fee_assignment__fee')
        serializer = self.get_serializer(payments, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_school(self, request):
        """Get all online payments for the school"""
        payments = OnlinePayment.objects.filter(school=request.user.school).select_related('student', 'school', 'fee_assignment', 'fee_assignment__fee')
        serializer = self.get_serializer(payments, many=True)
        return Response(serializer.data)


class SchoolExpenseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing school expenses
    """
    serializer_class = SchoolExpenseSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageExpenses()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'super_admin':
            return SchoolExpense.objects.all()
        else:
            # School admins and staff can see all expenses in their school
            return SchoolExpense.objects.filter(school=user.school)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return RecordSchoolExpenseSerializer
        return SchoolExpenseSerializer
    
    def perform_create(self, serializer):
        """Simplified - serializer handles creation and validation"""
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def by_school(self, request):
        """Get all expenses for the school"""
        expenses = SchoolExpense.objects.filter(school=request.user.school)
        serializer = self.get_serializer(expenses, many=True)
        return Response(serializer.data)


class SuperAdminBillingViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        from apps.schools.models import School
        invoices = Invoice.objects.all()
        payments = Payment.objects.all()
        online_payments = OnlinePayment.objects.all()

        total_invoice_amount = invoices.aggregate(total=Sum('amount'))['total'] or 0
        total_paid_amount = payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
        total_online_success = online_payments.filter(status='success').aggregate(total=Sum('amount'))['total'] or 0

        return Response({
            'total_schools': School.objects.count(),
            'total_invoices': invoices.count(),
            'total_payments': payments.count(),
            'total_invoice_amount': float(total_invoice_amount),
            'total_paid_amount': float(total_paid_amount),
            'total_online_success_amount': float(total_online_success),
            'payment_status_breakdown': list(payments.values('status').annotate(count=Count('id')).order_by('status'))
        })

    @action(detail=False, methods=['get'])
    def revenue_analytics(self, request):
        now = timezone.now()
        start_30 = now - timedelta(days=30)

        monthly_manual = ManualPayment.objects.filter(payment_date__gte=start_30).aggregate(total=Sum('amount'))['total'] or 0
        monthly_online = OnlinePayment.objects.filter(created_at__gte=start_30, status='success').aggregate(total=Sum('amount'))['total'] or 0
        monthly_invoice_paid = Payment.objects.filter(created_at__gte=start_30, status='completed').aggregate(total=Sum('amount'))['total'] or 0

        return Response({
            'last_30_days': {
                'manual_payments': float(monthly_manual),
                'online_payments': float(monthly_online),
                'invoice_payments': float(monthly_invoice_paid),
                'total_revenue': float(monthly_manual + monthly_online + monthly_invoice_paid),
            }
        })

    @action(detail=False, methods=['post'])
    def assign_plan(self, request):
        from apps.schools.models import School, Plan, Subscription

        school_id = request.data.get('school_id')
        plan_id = request.data.get('plan_id')
        end_date = request.data.get('end_date')

        if not school_id or not plan_id or not end_date:
            return Response({'error': 'school_id, plan_id, end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            school = School.objects.get(id=school_id)
            plan = Plan.objects.get(id=plan_id)
        except (School.DoesNotExist, Plan.DoesNotExist):
            return Response({'error': 'Invalid school or plan'}, status=status.HTTP_400_BAD_REQUEST)

        school.plan = plan
        school.save(update_fields=['plan', 'updated_at'])

        subscription, _ = Subscription.objects.get_or_create(
            school=school,
            defaults={'plan': plan, 'status': 'active', 'end_date': end_date}
        )
        subscription.plan = plan
        subscription.status = 'active'
        subscription.end_date = end_date
        subscription.save()

        return Response({'status': 'success', 'message': 'Plan assigned successfully'})

    @action(detail=False, methods=['get'])
    def gateway_config(self, request):
        return Response({
            'stripe': {'enabled': False, 'public_key_configured': False},
            'paystack': {'enabled': True, 'public_key_configured': True}
        })
