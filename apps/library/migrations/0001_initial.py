from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('academics', '__first__'),
        ('schools', '__first__'),
        ('users', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LibraryCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='library_categories', to='schools.school')),
            ],
            options={
                'db_table': 'library_category',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='LibraryBook',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('author', models.CharField(blank=True, default='', max_length=255)),
                ('isbn', models.CharField(blank=True, default='', max_length=32)),
                ('total_copies', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='books', to='library.librarycategory')),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='library_books', to='schools.school')),
            ],
            options={
                'db_table': 'library_book',
                'ordering': ['title', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LibraryLoan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('issued_at', models.DateField(auto_now_add=True)),
                ('due_date', models.DateField()),
                ('returned_at', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loans', to='library.librarybook')),
                ('class_obj', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_loans', to='academics.class')),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_loans_issued', to=settings.AUTH_USER_MODEL)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='library_loans', to='schools.school')),
                ('student', models.ForeignKey(limit_choices_to={'role': 'student'}, on_delete=django.db.models.deletion.PROTECT, related_name='library_loans', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'library_loan',
                'ordering': ['due_date', '-issued_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='librarycategory',
            constraint=models.UniqueConstraint(fields=('school', 'name'), name='library_category_school_name_uniq'),
        ),
        migrations.AddIndex(
            model_name='librarybook',
            index=models.Index(fields=['school', 'title'], name='library_book_school_title_idx'),
        ),
        migrations.AddIndex(
            model_name='libraryloan',
            index=models.Index(fields=['school', 'returned_at', 'due_date'], name='library_loan_school_due_idx'),
        ),
        migrations.AddIndex(
            model_name='libraryloan',
            index=models.Index(fields=['book', 'returned_at'], name='library_loan_book_active_idx'),
        ),
        migrations.AddConstraint(
            model_name='libraryloan',
            constraint=models.CheckConstraint(check=models.Q(('due_date__gte', models.F('issued_at'))), name='library_loan_due_after_issue'),
        ),
    ]
