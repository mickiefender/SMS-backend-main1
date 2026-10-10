from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from apps.academics.models import StudentClass
from apps.library.models import LibraryBook, LibraryCategory, LibraryLoan
from apps.library.serializers import (
    IssueBookSerializer,
    LibraryBookSerializer,
    LibraryCategorySerializer,
    LibraryLoanSerializer,
    books_with_availability,
    categories_with_counts,
)
from core.permissions import user_has_permission


class LibraryPermission(IsAuthenticated):
    permission_by_action = {}
    default_permissions = ()

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        if user.role in ('super_admin', 'school_admin'):
            return user.school_id is not None
        if not user.school_id:
            return False
        required = view.permission_by_action.get(
            getattr(view, 'action', None),
            view.default_permissions,
        )
        if isinstance(required, str):
            required = (required,)
        return bool(required) and user_has_permission(user, *required)


class LibraryCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = LibraryCategorySerializer
    permission_classes = [LibraryPermission]
    permission_by_action = {
        'list': ('manage_library_categories', 'manage_materials'),
        'retrieve': ('manage_library_categories', 'manage_materials'),
        'create': 'manage_library_categories',
        'update': 'manage_library_categories',
        'partial_update': 'manage_library_categories',
        'destroy': 'manage_library_categories',
    }

    def get_queryset(self):
        return categories_with_counts(
            LibraryCategory.objects.filter(school_id=self.request.user.school_id)
        )

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.books.exists():
            raise ValidationError({'detail': 'Move or remove this category’s books before deleting it.'})
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LibraryBookViewSet(viewsets.ModelViewSet):
    serializer_class = LibraryBookSerializer
    permission_classes = [LibraryPermission]
    permission_by_action = {
        'list': 'manage_materials',
        'retrieve': 'manage_materials',
        'create': 'manage_materials',
        'update': 'manage_materials',
        'partial_update': 'manage_materials',
        'destroy': 'manage_materials',
        'issue': 'manage_issued_books',
    }

    def get_queryset(self):
        queryset = LibraryBook.objects.filter(school_id=self.request.user.school_id)
        category_id = self.request.query_params.get('category')
        search = self.request.query_params.get('search', '').strip()
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(author__icontains=search)
                | Q(isbn__icontains=search)
            )
        return books_with_availability(queryset.select_related('category'))

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def perform_update(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        book = self.get_object()
        if book.loans.exists():
            raise ValidationError({'detail': 'Books with loan history cannot be deleted. Set the copy count to zero instead.'})
        book.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def issue(self, request, pk=None):
        with transaction.atomic():
            book = get_object_or_404(
                LibraryBook.objects.select_for_update().filter(school_id=request.user.school_id),
                pk=pk,
            )
            serializer = IssueBookSerializer(
                data=request.data,
                context={'request': request, 'today': timezone.localdate()},
            )
            serializer.is_valid(raise_exception=True)
            active_loans = book.loans.filter(returned_at__isnull=True).count()
            if active_loans >= book.total_copies:
                raise ValidationError({'detail': 'No copies of this book are currently available.'})

            student_id = serializer.validated_data['student_id']
            if book.loans.filter(student_id=student_id, returned_at__isnull=True).exists():
                raise ValidationError({'detail': 'This student already has an active loan for this book.'})

            class_assignment = StudentClass.objects.filter(
                student_id=student_id,
                class_obj__school_id=request.user.school_id,
                is_active=True,
            ).select_related('class_obj').first()

            loan = LibraryLoan.objects.create(
                school=request.user.school,
                book=book,
                student_id=student_id,
                class_obj=class_assignment.class_obj if class_assignment else None,
                issued_by=request.user,
                due_date=serializer.validated_data['due_date'],
            )

        return Response(LibraryLoanSerializer(loan).data, status=status.HTTP_201_CREATED)


class LibraryLoanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LibraryLoanSerializer
    permission_classes = [LibraryPermission]
    permission_by_action = {
        'list': 'manage_issued_books',
        'retrieve': 'manage_issued_books',
        'return_book': 'manage_issued_books',
    }

    def get_queryset(self):
        queryset = LibraryLoan.objects.filter(
            school_id=self.request.user.school_id,
            returned_at__isnull=True,
        ).select_related('book', 'student', 'class_obj')
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(book__title__icontains=search)
                | Q(student__first_name__icontains=search)
                | Q(student__last_name__icontains=search)
                | Q(student__username__icontains=search)
                | Q(class_obj__name__icontains=search)
            )
        return queryset

    @action(detail=True, methods=['post'], url_path='return')
    def return_book(self, request, pk=None):
        with transaction.atomic():
            loan = get_object_or_404(
                LibraryLoan.objects.select_for_update().filter(
                    school_id=request.user.school_id,
                    returned_at__isnull=True,
                ).select_related('book', 'student', 'class_obj'),
                pk=pk,
            )
            loan.returned_at = timezone.localdate()
            loan.save(update_fields=['returned_at'])
        return Response(LibraryLoanSerializer(loan).data)
