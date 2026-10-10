from django.conf import settings
from django.db import models
from django.db.models import Q


class LibraryCategory(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='library_categories',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'library_category'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'name'], name='library_category_school_name_uniq'),
        ]

    def __str__(self):
        return self.name


class LibraryBook(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='library_books',
    )
    category = models.ForeignKey(
        LibraryCategory,
        on_delete=models.PROTECT,
        related_name='books',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True, default='')
    isbn = models.CharField(max_length=32, blank=True, default='')
    total_copies = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'library_book'
        ordering = ['title', 'id']
        indexes = [models.Index(fields=['school', 'title'], name='library_book_school_title_idx')]

    def __str__(self):
        return self.title

    @property
    def available_copies(self):
        active_loans = self.loans.filter(returned_at__isnull=True).count()
        return max(0, self.total_copies - active_loans)


class LibraryLoan(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='library_loans',
    )
    book = models.ForeignKey(
        LibraryBook,
        on_delete=models.PROTECT,
        related_name='loans',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='library_loans',
        limit_choices_to={'role': 'student'},
    )
    class_obj = models.ForeignKey(
        'academics.Class',
        on_delete=models.SET_NULL,
        related_name='library_loans',
        null=True,
        blank=True,
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='library_loans_issued',
        null=True,
        blank=True,
    )
    issued_at = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    returned_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'library_loan'
        ordering = ['due_date', '-issued_at']
        indexes = [
            models.Index(fields=['school', 'returned_at', 'due_date'], name='library_loan_school_due_idx'),
            models.Index(fields=['book', 'returned_at'], name='library_loan_book_active_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(due_date__gte=models.F('issued_at')),
                name='library_loan_due_after_issue',
            ),
        ]

    @property
    def borrower_name(self):
        return self.student.get_full_name().strip() or self.student.username

    @property
    def class_name(self):
        return self.class_obj.name if self.class_obj else ''
