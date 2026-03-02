import hashlib
import hmac
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    FeeStructure, Invoice, InvoiceItem,
    Payment, PaymentReceipt, PaystackWebhookLog
)
from .serializers import (
    FeeStructureSerializer, InvoiceSerializer, InvoiceCreateSerializer,
    InitializePaymentSerializer, PaymentSerializer, PaymentReceiptSerializer,
    VerifyPaymentSerializer, RecordOfflinePaymentSerializer
)
from .utils import PaystackAPI

logger = logging.getLogger(__name__)
User = get_user_model()


class FeeStructureViewSet(viewsets.ModelViewSet):
    """ViewSet for managing fee structures."""
    serializer_class = FeeStructureSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = FeeStructure.objects.filter(is_active=True)
        school_id = self.request.query_params.get('school_id')
        class_level_id = self.request.query_params.get('class_level_id')
        academic_year = self.request.query_params.get('academic_year')
        term = self.request.query_params.get('term')

        if school_id:
            queryset = queryset.filter(school_id=school_id)
        if class_level_id:
            queryset = queryset.filter(class_level_id=class_level_id)
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)
        if term:
            queryset = queryset.filter(term=term)

        return queryset


class InvoiceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing invoices."""
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Invoice.objects.select_related('student', 'school').prefetch_related('items')
        school_id = self.request.query_params.get('school_id')
        student_id = self.request.query_params.get('student_id')
        status_filter = self.request.query_params.get('status')
        academic_year = self.request.query_params.get('academic_year')
        term = self.request.query_params.get('term')

        if school_id:
            queryset = queryset.filter(school_id=school_id)
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)
        if term:
            queryset = queryset.filter(term=term)

        return queryset

    @action(detail=False, methods=['post'])
    def create_invoice(self, request):
        """Create an invoice for a student with fee items."""
        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        student_id = data['student_id']
        academic_year = data['academic_year']
        term = data['term']

        try:
            student = User.objects.get(id=student_id, role='student')
        except User.DoesNotExist:
            return Response(
                {'error': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check for existing unpaid invoice
        existing = Invoice.objects.filter(
            student=student,
            academic_year=academic_year,
            term=term,
            status__in=['draft', 'sent', 'partially_paid']
        ).first()

        if existing:
            return Response(
                {
                    'error': 'An active invoice already exists for this student/term',
                    'invoice_id': str(existing.id)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Get applicable fee structures
            if 'fee_structure_ids' in data and data['fee_structure_ids']:
                fee_structures = FeeStructure.objects.filter(
                    id__in=data['fee_structure_ids'],
                    is_active=True
                )
            else:
                # Get student's class from StudentClass assignment
                from apps.academics.models import StudentClass
                student_class = StudentClass.objects.filter(
                    student=student, is_active=True
                ).first()

                fee_structures = FeeStructure.objects.filter(
                    school=student.school,
                    academic_year=academic_year,
                    term=term,
                    is_active=True,
                    is_compulsory=True
                )

                if student_class:
                    fee_structures = fee_structures.filter(
                        models.Q(class_level=student_class.class_obj) |
                        models.Q(class_level__isnull=True)
                    )
                else:
                    fee_structures = fee_structures.filter(class_level__isnull=True)

            if not fee_structures.exists():
                return Response(
                    {'error': 'No fee structures found for the given criteria'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create invoice
            invoice = Invoice.objects.create(
                school=student.school,
                student=student,
                academic_year=academic_year,
                term=term,
                due_date=data.get('due_date'),
                notes=data.get('notes', ''),
                status='draft'
            )

            # Create invoice items
            total = Decimal('0.00')
            for fee in fee_structures:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    fee_structure=fee,
                    description=fee.name,
                    amount=fee.amount
                )
                total += fee.amount

            invoice.total_amount = total
            invoice.balance = total
            invoice.save()

        return Response(
            InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def send_invoice(self, request, pk=None):
        """Mark invoice as sent."""
        invoice = self.get_object()
        if invoice.status == 'draft':
            invoice.status = 'sent'
            invoice.save()
        return Response(InvoiceSerializer(invoice).data)


class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing payments."""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Payment.objects.select_related('invoice', 'student', 'school')
        school_id = self.request.query_params.get('school_id')
        student_id = self.request.query_params.get('student_id')
        status_filter = self.request.query_params.get('status')
        payment_method = self.request.query_params.get('payment_method')

        if school_id:
            queryset = queryset.filter(school_id=school_id)
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        return queryset

    @action(detail=False, methods=['post'])
    def initialize(self, request):
        """Initialize a Paystack payment transaction."""
        serializer = InitializePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            invoice = Invoice.objects.get(id=data['invoice_id'])
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'Invoice not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if invoice.status in ['paid', 'cancelled']:
            return Response(
                {'error': f'Invoice is already {invoice.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Determine amount (use provided or invoice balance)
        amount = data.get('amount', invoice.balance)
        if amount <= 0:
            return Response(
                {'error': 'Payment amount must be greater than zero'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if amount > invoice.balance:
            return Response(
                {'error': f'Amount exceeds invoice balance of ₦{invoice.balance}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create payment record
        payment = Payment.objects.create(
            invoice=invoice,
            school=invoice.school,
            student=invoice.student,
            amount=amount,
            payment_method='paystack',
            status='pending',
            paid_by_email=data['email'],
            metadata=data.get('metadata', {})
        )

        # Initialize Paystack transaction
        paystack = PaystackAPI()
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        callback_url = data.get('callback_url', f"{frontend_url}/payments/verify")

        paystack_data = paystack.initialize_transaction(
            email=data['email'],
            amount=amount,
            reference=payment.transaction_reference,
            callback_url=callback_url,
            metadata={
                'payment_id': str(payment.id),
                'invoice_id': str(invoice.id),
                'invoice_number': invoice.invoice_number,
                'student_id': str(invoice.student.id),
                'school_id': str(invoice.school.id),
                **data.get('metadata', {})
            }
        )

        if paystack_data.get('status'):
            tx_data = paystack_data['data']
            payment.paystack_reference = tx_data['reference']
            payment.paystack_access_code = tx_data['access_code']
            payment.paystack_authorization_url = tx_data['authorization_url']
            payment.save()

            return Response({
                'status': 'success',
                'message': 'Payment initialized',
                'data': {
                    'authorization_url': tx_data['authorization_url'],
                    'access_code': tx_data['access_code'],
                    'reference': tx_data['reference'],
                    'payment_id': str(payment.id),
                }
            })
        else:
            payment.status = 'failed'
            payment.save()
            return Response(
                {
                    'error': 'Failed to initialize payment',
                    'details': paystack_data.get('message', 'Unknown error')
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

    @action(detail=False, methods=['post'])
    def verify(self, request):
        """Verify a Paystack payment."""
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reference = serializer.validated_data['reference']

        try:
            payment = Payment.objects.get(
                models.Q(paystack_reference=reference) |
                models.Q(transaction_reference=reference)
            )
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Payment not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if payment.status == 'success':
            return Response({
                'status': 'success',
                'message': 'Payment already verified',
                'data': PaymentSerializer(payment).data
            })

        paystack = PaystackAPI()
        verification = paystack.verify_transaction(reference)

        if verification.get('status') and verification['data']['status'] == 'success':
            tx_data = verification['data']

            with transaction.atomic():
                payment.status = 'success'
                payment.paystack_transaction_id = str(tx_data.get('id', ''))
                payment.paystack_channel = tx_data.get('channel', '')
                payment.paystack_paid_at = tx_data.get('paid_at')
                payment.paystack_fees = Decimal(str(tx_data.get('fees', 0))) / 100
                payment.save()

                # Update invoice
                invoice = payment.invoice
                invoice.amount_paid += payment.amount
                invoice.save()

                # Generate receipt
                self._generate_receipt(payment)

            return Response({
                'status': 'success',
                'message': 'Payment verified successfully',
                'data': PaymentSerializer(payment).data
            })
        else:
            payment.status = 'failed'
            payment.save()
            return Response(
                {
                    'status': 'failed',
                    'message': 'Payment verification failed',
                    'details': verification.get('message', 'Unknown error')
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def record_offline(self, request):
        """Record an offline/manual payment."""
        serializer = RecordOfflinePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            invoice = Invoice.objects.get(id=data['invoice_id'])
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'Invoice not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        amount = data['amount']
        if amount > invoice.balance:
            return Response(
                {'error': f'Amount exceeds invoice balance of ₦{invoice.balance}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            payment = Payment.objects.create(
                invoice=invoice,
                school=invoice.school,
                student=invoice.student,
                amount=amount,
                payment_method=data['payment_method'],
                status='success',
                paid_by=data.get('paid_by', ''),
                paid_by_phone=data.get('paid_by_phone', ''),
                notes=data.get('notes', ''),
            )

            invoice.amount_paid += amount
            invoice.save()

            self._generate_receipt(payment)

        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED
        )

    def _generate_receipt(self, payment):
        """Generate a receipt for a successful payment."""
        receipt_data = {
            'payment_id': str(payment.id),
            'invoice_number': payment.invoice.invoice_number,
            'student_name': payment.student.get_full_name(),
            'school_name': payment.school.name,
            'amount': str(payment.amount),
            'payment_method': payment.get_payment_method_display(),
            'transaction_reference': payment.transaction_reference,
            'date': payment.created_at.isoformat(),
        }

        PaymentReceipt.objects.create(
            payment=payment,
            receipt_data=receipt_data
        )


class PaystackWebhookView(APIView):
    """Handle Paystack webhook events."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        # Verify webhook signature
        payload = request.body
        signature = request.headers.get('X-Paystack-Signature', '')

        webhook_secret = getattr(settings, 'PAYSTACK_WEBHOOK_SECRET', '')
        if webhook_secret:
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Invalid Paystack webhook signature")
                return Response(
                    {'error': 'Invalid signature'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return Response(
                {'error': 'Invalid JSON'},
                status=status.HTTP_400_BAD_REQUEST
            )

        event_type = event.get('event', '')
        data = event.get('data', {})
        reference = data.get('reference', '')

        # Log the webhook
        webhook_log = PaystackWebhookLog.objects.create(
            event_type=event_type,
            payload=event,
            reference=reference,
            ip_address=self._get_client_ip(request)
        )

        try:
            if event_type == 'charge.success':
                self._handle_charge_success(data, webhook_log)
            elif event_type == 'charge.failed':
                self._handle_charge_failed(data, webhook_log)
            elif event_type == 'transfer.success':
                self._handle_transfer_success(data, webhook_log)
            elif event_type == 'transfer.failed':
                self._handle_transfer_failed(data, webhook_log)
            else:
                logger.info(f"Unhandled webhook event: {event_type}")

            webhook_log.processed = True
            webhook_log.save()

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            webhook_log.processing_error = str(e)
            webhook_log.save()

        return Response({'status': 'ok'}, status=status.HTTP_200_OK)

    def _handle_charge_success(self, data, webhook_log):
        """Handle successful charge event."""
        reference = data.get('reference')

        try:
            payment = Payment.objects.get(
                models.Q(paystack_reference=reference) |
                models.Q(transaction_reference=reference)
            )
        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for reference: {reference}")
            webhook_log.processing_error = f"Payment not found: {reference}"
            return

        if payment.status == 'success':
            return  # Already processed

        with transaction.atomic():
            payment.status = 'success'
            payment.paystack_transaction_id = str(data.get('id', ''))
            payment.paystack_channel = data.get('channel', '')
            payment.paystack_paid_at = data.get('paid_at')
            fees = data.get('fees', 0)
            payment.paystack_fees = Decimal(str(fees)) / 100 if fees else Decimal('0')
            payment.save()

            # Update invoice
            invoice = payment.invoice
            invoice.amount_paid += payment.amount
            invoice.save()

    def _handle_charge_failed(self, data, webhook_log):
        """Handle failed charge event."""
        reference = data.get('reference')
        try:
            payment = Payment.objects.get(
                models.Q(paystack_reference=reference) |
                models.Q(transaction_reference=reference)
            )
            payment.status = 'failed'
            payment.save()
        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for failed charge: {reference}")

    def _handle_transfer_success(self, data, webhook_log):
        """Handle successful transfer (for refunds, etc.)."""
        logger.info(f"Transfer success: {data.get('reference')}")

    def _handle_transfer_failed(self, data, webhook_log):
        """Handle failed transfer."""
        logger.info(f"Transfer failed: {data.get('reference')}")

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class PaymentDashboardView(APIView):
    """Dashboard statistics for payments."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum, Count, Q

        school_id = request.query_params.get('school_id')
        academic_year = request.query_params.get('academic_year')
        term = request.query_params.get('term')

        filters = {}
        if school_id:
            filters['school_id'] = school_id
        if academic_year:
            filters['invoice__academic_year'] = academic_year
        if term:
            filters['invoice__term'] = term

        payments = Payment.objects.filter(**filters)

        total_collected = payments.filter(status='success').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        total_pending = payments.filter(status='pending').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        invoice_filters = {}
        if school_id:
            invoice_filters['school_id'] = school_id
        if academic_year:
            invoice_filters['academic_year'] = academic_year
        if term:
            invoice_filters['term'] = term

        invoices = Invoice.objects.filter(**invoice_filters)

        total_billed = invoices.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0')

        total_outstanding = invoices.exclude(status__in=['paid', 'cancelled']).aggregate(
            total=Sum('balance')
        )['total'] or Decimal('0')

        payment_count = payments.filter(status='success').count()

        recent_payments = PaymentSerializer(
            payments.filter(status='success').order_by('-created_at')[:10],
            many=True
        ).data

        # Payment method breakdown
        method_breakdown = payments.filter(status='success').values(
            'payment_method'
        ).annotate(
            count=Count('id'),
            total=Sum('amount')
        )

        return Response({
            'total_billed': str(total_billed),
            'total_collected': str(total_collected),
            'total_pending': str(total_pending),
            'total_outstanding': str(total_outstanding),
            'collection_rate': str(
                round((total_collected / total_billed * 100), 2) if total_billed > 0 else 0
            ),
            'payment_count': payment_count,
            'recent_payments': recent_payments,
            'method_breakdown': list(method_breakdown),
        })
