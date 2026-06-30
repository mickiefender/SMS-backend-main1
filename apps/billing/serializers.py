from rest_framework import serializers
from .models import Fee, StudentFeeAssignment, ClassFeeAssignment, SchoolFeeAssignment, Invoice, Payment, ManualPayment, OnlinePayment, SchoolExpense


class FeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fee
        fields = ['id', 'school', 'name', 'description', 'amount', 'fee_type', 'is_active', 'is_mandatory', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'created_at', 'updated_at']


class SchoolFeeAssignmentSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)
    fee_name = serializers.CharField(source='fee.name', read_only=True)
    fee_details = FeeSerializer(source='fee', read_only=True)

    class Meta:
        model = SchoolFeeAssignment
        fields = ['id', 'school', 'school_name', 'fee', 'fee_name', 'fee_details', 'amount', 'due_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'school_name', 'fee_name', 'fee_details', 'created_at', 'updated_at']
        extra_kwargs = {
            'school': {'required': False}
        }


class ClassFeeAssignmentSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source='class_obj.name', read_only=True)
    fee_name = serializers.CharField(source='fee.name', read_only=True)
    fee_details = FeeSerializer(source='fee', read_only=True)

    class Meta:
        model = ClassFeeAssignment
        fields = ['id', 'class_obj', 'class_name', 'fee', 'fee_name', 'fee_details', 'amount', 'due_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'class_name', 'fee_name', 'fee_details', 'created_at', 'updated_at']


class StudentFeeAssignmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    fee_name = serializers.CharField(source='fee.name', read_only=True)
    fee_details = FeeSerializer(source='fee', read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = StudentFeeAssignment
        fields = ['id', 'student', 'student_name', 'fee', 'fee_name', 'fee_details', 'amount', 'amount_paid', 'balance', 'due_date', 'paid', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'student_name', 'fee_name', 'fee_details', 'status', 'created_at', 'updated_at']
        validators = []
    
    def validate(self, data):
        student = data.get('student')
        fee = data.get('fee')
        if student and fee:
            student_id = student.id
            fee_id = fee.id
            try:
                existing = StudentFeeAssignment.objects.get(student_id=student_id, fee_id=fee_id)
                data['id'] = existing.id
            except StudentFeeAssignment.DoesNotExist:
                pass
        return data

    def get_balance(self, obj):
        return obj.balance


class ManualPaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    fee_name = serializers.CharField(source='fee_assignment.fee.name', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)

    class Meta:
        model = ManualPayment
        fields = ['id', 'school', 'student', 'student_name', 'fee_assignment', 'fee_name', 'amount', 'payment_method', 'payment_method_display', 'receipt_number', 'notes', 'recorded_by', 'recorded_by_name', 'payment_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'receipt_number', 'recorded_by', 'payment_date', 'created_at', 'updated_at']


class RecordManualPaymentSerializer(serializers.ModelSerializer):
    """Serializer for recording manual payments - input + output"""
    student_id = serializers.IntegerField(write_only=True)
    fee_assignment_id = serializers.IntegerField(write_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_method = serializers.ChoiceField(choices=ManualPayment.PAYMENT_METHOD_CHOICES, default='cash')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    fee_name = serializers.CharField(source='fee_assignment.fee.name', read_only=True)
    receipt_number = serializers.CharField(read_only=True)
    payment_date = serializers.DateTimeField(read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)
    
    class Meta:
        model = ManualPayment
        fields = [
            'id', 'school', 'student', 'student_id', 'student_name', 
            'fee_assignment', 'fee_assignment_id', 'fee_name',
            'amount', 'payment_method', 'receipt_number', 
            'notes', 'recorded_by', 'recorded_by_name', 'payment_date', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'student', 'fee_assignment', 
                          'receipt_number', 'payment_date', 'recorded_by', 
                          'created_at', 'updated_at']
    
    def create(self, validated_data):
        """Create manual payment and update fee assignment"""
        from django.contrib.auth import get_user_model
        from .models import StudentFeeAssignment
        User = get_user_model()
        
        # Extract input data
        student_id = validated_data.pop('student_id')
        fee_assignment_id = validated_data.pop('fee_assignment_id')
        amount = validated_data.pop('amount')
        
        # Fetch student
        try:
            student = User.objects.get(id=student_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"student_id": f"Student not found with ID: {student_id}"})
        
        if student.role != 'student':
            raise serializers.ValidationError({"student_id": "User is not a student"})
        
        # Fetch fee assignment
        try:
            fee_assignment = StudentFeeAssignment.objects.get(id=fee_assignment_id)
        except StudentFeeAssignment.DoesNotExist:
            raise serializers.ValidationError({"fee_assignment_id": f"Fee assignment not found with ID: {fee_assignment_id}"})
        
        if fee_assignment.student != student:
            raise serializers.ValidationError({"fee_assignment_id": "Fee assignment does not belong to the specified student"})
        
        if amount > fee_assignment.balance:
            raise serializers.ValidationError({"amount": f"Amount {amount} exceeds remaining balance {fee_assignment.balance}"})
        
        # Update fee assignment amount_paid
        current_paid = fee_assignment.amount_paid or 0
        fee_assignment.amount_paid = current_paid + amount
        fee_assignment.save()
        
        # Create manual payment
        manual_payment = ManualPayment.objects.create(
            school=self.context['request'].user.school,
            student=student,
            fee_assignment=fee_assignment,
            amount=amount,
            payment_method=validated_data.get('payment_method', 'cash'),
            notes=validated_data.get('notes', ''),
            recorded_by=self.context['request'].user
        )
        
        return manual_payment


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class OnlinePaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    fee_name = serializers.CharField(source='fee_assignment.fee.name', read_only=True)
    payment_method_display = serializers.SerializerMethodField()
    
    class Meta:
        model = OnlinePayment
        fields = [
            'id', 'school', 'student', 'student_name', 'fee_assignment', 'fee_name',
            'amount', 'payment_method', 'payment_method_display', 'transaction_id',
            'reference', 'status', 'receipt_number', 'notes', 'channel', 'currency',
            'paid_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'receipt_number', 'status', 'created_at', 'updated_at']
    
    def get_payment_method_display(self, obj):
        return obj.get_payment_method_display() if obj.payment_method else 'Paystack'


class RecordOnlinePaymentSerializer(serializers.Serializer):
    """Serializer for recording an online payment from frontend"""
    student_id = serializers.IntegerField()
    fee_assignment_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    reference = serializers.CharField(max_length=100)
    transaction_id = serializers.CharField(max_length=100)
    channel = serializers.CharField(max_length=50, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=OnlinePayment.STATUS_CHOICES, default='success')
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class SchoolExpenseSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)

    class Meta:
        model = SchoolExpense
        fields = [
            'id', 'school', 'school_name', 'category', 'category_display', 
            'amount', 'expense_date', 'description', 'expense_number', 
            'recorded_by', 'recorded_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'expense_number', 'recorded_by', 'created_at', 'updated_at']


class RecordSchoolExpenseSerializer(serializers.ModelSerializer):
    """Serializer for recording school expenses"""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    category = serializers.ChoiceField(choices=SchoolExpense.EXPENSE_CATEGORY_CHOICES)
    expense_date = serializers.DateField()
    description = serializers.CharField(required=False, allow_blank=True, default='')
    
    school_name = serializers.CharField(source='school.name', read_only=True)
    expense_number = serializers.CharField(read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)

    class Meta:
        model = SchoolExpense
        fields = [
            'id', 'school', 'school_name', 'category', 
            'amount', 'expense_date', 'description', 'expense_number', 
            'recorded_by', 'recorded_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'school_name', 'expense_number', 'recorded_by', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """Create school expense"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        expense = SchoolExpense.objects.create(
            school=self.context['request'].user.school,
            **validated_data,
            recorded_by=self.context['request'].user
        )
        return expense
