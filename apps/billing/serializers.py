from rest_framework import serializers
from apps.billing.models import Invoice, Payment, Fee
from apps.academics.models import SchoolFees, Class, StudentClass
from apps.users.models import User


class FeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fee
        fields = '__all__'


class StudentFeeAssignSerializer(serializers.Serializer):
    fee = serializers.PrimaryKeyRelatedField(queryset=Fee.objects.all())
    student = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='student'), required=False)
    class_obj = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all(), required=False)

    def validate(self, data):
        if not data.get('student') and not data.get('class_obj'):
            raise serializers.ValidationError("Either student or class must be provided.")
        if data.get('student') and data.get('class_obj'):
            raise serializers.ValidationError("Provide either student or class, not both.")
        return data

    def create(self, validated_data):
        fee = validated_data.get('fee')
        student = validated_data.get('student')
        class_obj = validated_data.get('class_obj')

        if student:
            # Assign fee to a single student
            student_class = StudentClass.objects.filter(student=student, is_active=True).first()
            if not student_class:
                raise serializers.ValidationError("Student is not enrolled in any active class.")
            
            school_fee = SchoolFees.objects.create(
                school=fee.school,
                student=student,
                class_obj=student_class.class_obj,
                title=fee.name,
                amount_due=fee.amount,
                due_date='2024-12-31',  # You might want to make this dynamic
                description=fee.description
            )
            return school_fee

        if class_obj:
            # Assign fee to all students in a class
            students_in_class = StudentClass.objects.filter(class_obj=class_obj, is_active=True)
            school_fees = []
            for student_class in students_in_class:
                school_fee = SchoolFees.objects.create(
                    school=fee.school,
                    student=student_class.student,
                    class_obj=class_obj,
                    title=fee.name,
                    amount_due=fee.amount,
                    due_date='2024-12-31',  # You might want to make this dynamic
                    description=fee.description
                )
                school_fees.append(school_fee)
            return school_fees


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
