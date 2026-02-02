from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import connection
from apps.schools.models import School

User = get_user_model()


class Command(BaseCommand):
    help = 'Setup existing Supabase database for Django'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-superuser',
            action='store_true',
            help='Create a superuser account',
        )
        parser.add_argument(
            '--test-connection',
            action='store_true',
            help='Test database connection',
        )

    def handle(self, *args, **options):
        # Test connection first
        if options['test_connection']:
            self.test_database_connection()
            return

        # Fake all migrations as already applied
        self.stdout.write(self.style.WARNING('Faking migrations...'))
        from django.core.management import call_command
        try:
            call_command('migrate', '--fake-initial', verbosity=0)
            self.stdout.write(self.style.SUCCESS('✓ Migrations faked successfully'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Note: {e}'))

        # Create superuser if requested
        if options['create_superuser']:
            self.create_superuser()

        self.stdout.write(self.style.SUCCESS('\n✓ Database setup complete!'))
        self.stdout.write('Next steps:')
        self.stdout.write('  1. Run: python manage.py runserver')
        self.stdout.write('  2. Visit: http://localhost:8000/api/')

    def test_database_connection(self):
        """Test connection to Supabase database"""
        self.stdout.write('Testing database connection...')
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                result = cursor.fetchone()
            if result:
                self.stdout.write(self.style.SUCCESS('✓ Database connection successful!'))
                # Try to count users
                try:
                    user_count = User.objects.count()
                    self.stdout.write(f'✓ Found {user_count} users in database')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠ Could not query users: {e}'))
            else:
                self.stdout.write(self.style.ERROR('✗ Database connection test failed'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Connection error: {e}'))

    def create_superuser(self):
        """Create a superuser account interactively"""
        import getpass
        
        self.stdout.write('\n--- Create Superuser ---')
        username = input('Username: ').strip()
        email = input('Email: ').strip()
        password = getpass.getpass('Password: ')
        password_confirm = getpass.getpass('Confirm Password: ')

        if password != password_confirm:
            self.stdout.write(self.style.ERROR('✗ Passwords do not match'))
            return

        try:
            # Create primary school first if it doesn't exist
            school, created = School.objects.get_or_create(
                name='Main School',
                defaults={'code': 'MAIN', 'country': 'USA', 'status': 'active'}
            )
            if created:
                self.stdout.write(f'✓ Created primary school')

            # Create superuser
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                role='super_admin',
                school=school,
                first_name=username.title()
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Superuser "{username}" created successfully'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error creating superuser: {e}'))
