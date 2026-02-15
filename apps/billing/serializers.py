from rest_framework import serializers
from .models import Fee, StudentFeeAssignment, ClassFeeAssignment, SchoolFeeAssignment, Invoice, Payment


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

    class Meta:
        model = StudentFeeAssignment
        fields = ['id', 'student', 'student_name', 'fee', 'fee_name', 'fee_details', 'amount', 'due_date', 'paid', 'created_at', 'updated_at']
        read_only_fields = ['id', 'student_name', 'fee_name', 'fee_details', 'created_at', 'updated_at']


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
