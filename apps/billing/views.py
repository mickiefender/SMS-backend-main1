from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsSchoolAdminOrHigher
from apps.billing.models import Invoice, Payment, FeeType, StudentFee, ClassFee
from apps.billing.serializers import InvoiceSerializer, PaymentSerializer, FeeTypeSerializer, StudentFeeSerializer, ClassFeeSerializer


class FeeTypeViewSet(viewsets.ModelViewSet):
    serializer_class = FeeTypeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return FeeType.objects.all()
        return FeeType.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class StudentFeeViewSet(viewsets.ModelViewSet):
    serializer_class = StudentFeeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            qs = StudentFee.objects.all()
        else:
            # Filter by class's school instead of student's school
            qs = StudentFee.objects.filter(class_obj__school=self.request.user.school)
        
        print(f"[v0] StudentFeeViewSet - User: {self.request.user.email}, School: {self.request.user.school}")
        print(f"[v0] StudentFeeViewSet - Queryset count: {qs.count()}")
        
        return qs


class ClassFeeViewSet(viewsets.ModelViewSet):
    serializer_class = ClassFeeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            qs = ClassFee.objects.all()
        else:
            qs = ClassFee.objects.filter(class_obj__school=self.request.user.school)
        
        print(f"[v0] ClassFeeViewSet - User: {self.request.user.email}, Role: {self.request.user.role}, School: {self.request.user.school}")
        print(f"[v0] ClassFeeViewSet - Queryset count: {qs.count()}")
        print(f"[v0] ClassFeeViewSet - Data: {list(qs.values())}")
        
        return qs


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Invoice.objects.all()
        return Invoice.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Payment.objects.all()
        return Payment.objects.filter(invoice__school=self.request.user.school)
