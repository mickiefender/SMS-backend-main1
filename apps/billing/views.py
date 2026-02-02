from rest_framework import viewsets, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from core.permissions import IsSuperAdmin, IsSchoolAdmin
from apps.billing.models import Invoice, Payment, Fee
from apps.billing.serializers import InvoiceSerializer, PaymentSerializer, FeeSerializer, StudentFeeAssignSerializer


class FeeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing predefined fees.
    """
    serializer_class = FeeSerializer
    permission_classes = [IsAuthenticated, IsSchoolAdmin]

    def get_queryset(self):
        return Fee.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class AssignFeeView(generics.CreateAPIView):
    """
    View for assigning fees to students or classes.
    """
    serializer_class = StudentFeeAssignSerializer
    permission_classes = [IsAuthenticated, IsSchoolAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Invoice.objects.all()
        return Invoice.objects.filter(school=self.request.user.school)


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Payment.objects.all()
        return Payment.objects.filter(invoice__school=self.request.user.school)
