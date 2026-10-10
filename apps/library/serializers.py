from django.db.models import Count, Q
from rest_framework import serializers

from apps.library.models import LibraryBook, LibraryCategory, LibraryLoan
from apps.users.models import User


class LibraryCategorySerializer(serializers.ModelSerializer):
    book_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = LibraryCategory
        fields = ['id', 'name', 'description', 'book_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'book_count', 'created_at', 'updated_at']

    def validate_name(self, value):
        school_id = self.context['request'].user.school_id
        existing = LibraryCategory.objects.filter(school_id=school_id, name__iexact=value.strip())
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError('A category with this name already exists.')
        return value.strip()


class LibraryBookSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    available_copies = serializers.SerializerMethodField()

    class Meta:
        model = LibraryBook
        fields = [
            'id', 'title', 'author', 'isbn', 'category', 'category_name',
            'total_copies', 'available_copies', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'category_name', 'available_copies', 'created_at', 'updated_at']

    def get_available_copies(self, obj):
        active_loans = getattr(obj, 'active_loan_count', None)
        if active_loans is None:
            active_loans = obj.loans.filter(returned_at__isnull=True).count()
        return max(0, obj.total_copies - active_loans)

    def get_category_name(self, obj):
        return obj.category.name if obj.category else ''

    def validate_category(self, category):
        if category and category.school_id != self.context['request'].user.school_id:
            raise serializers.ValidationError('Select a category from your school.')
        return category

    def validate(self, attrs):
        school_id = self.context['request'].user.school_id
        isbn = attrs.get('isbn', getattr(self.instance, 'isbn', '')).strip()
        total_copies = attrs.get('total_copies', getattr(self.instance, 'total_copies', 1))
        if self.instance:
            active_loans = self.instance.loans.filter(returned_at__isnull=True).count()
            if total_copies < active_loans:
                raise serializers.ValidationError({
                    'total_copies': f'Total copies cannot be less than the {active_loans} active loans.'
                })
        if isbn:
            existing = LibraryBook.objects.filter(school_id=school_id, isbn__iexact=isbn)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError({'isbn': 'A book with this ISBN already exists.'})
        attrs['isbn'] = isbn
        return attrs


class LibraryLoanSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    borrower = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    student_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = LibraryLoan
        fields = [
            'id', 'book', 'book_title', 'student_id', 'student_name', 'borrower',
            'class_name', 'issued_at', 'due_date', 'returned_at',
        ]
        read_only_fields = fields

    def get_borrower(self, obj):
        return obj.borrower_name

    def get_student_name(self, obj):
        return obj.borrower_name

    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else ''


class IssueBookSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    due_date = serializers.DateField()

    def validate_student_id(self, value):
        school_id = self.context['request'].user.school_id
        if not User.objects.filter(
            pk=value,
            school_id=school_id,
            role='student',
            student_profile__isnull=False,
        ).exists():
            raise serializers.ValidationError('Select a student from your school.')
        return value

    def validate(self, attrs):
        if attrs['due_date'] < self.context['today']:
            raise serializers.ValidationError({'due_date': 'Due date cannot be in the past.'})
        return attrs


def books_with_availability(queryset):
    return queryset.annotate(
        active_loan_count=Count(
            'loans',
            filter=Q(loans__returned_at__isnull=True),
        )
    )


def categories_with_counts(queryset):
    return queryset.annotate(book_count=Count('books', distinct=True))
