from rest_framework import serializers
from .models import FeeType, StudentFee, ClassFee, Invoice, Payment, Fee


class FeeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeType
        fields = ['id', 'name', 'description', 'amount', 'is_active', 'is_mandatory', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class StudentFeeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    fee_type_name = serializers.CharField(source='fee_type.name', read_only=True)
    class_name = serializers.CharField(source='class_obj.name', read_only=True)

    class Meta:
        model = StudentFee
        fields = ['id', 'student', 'student_name', 'class_name', 'fee_type', 'fee_type_name', 'amount', 'due_date', 'paid', 'created_at', 'updated_at']
        read_only_fields = ['id', 'student_name', 'class_name', 'fee_type_name', 'created_at', 'updated_at']


class ClassFeeSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source='class_obj.name', read_only=True)
    fee_type_name = serializers.CharField(source='fee_type.name', read_only=True)

    class Meta:
        model = ClassFee
        fields = ['id', 'class_obj', 'class_name', 'fee_type', 'fee_type_name', 'amount', 'due_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'class_name', 'fee_type_name', 'created_at', 'updated_at']


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


class FeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fee
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
