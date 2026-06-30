from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(choices=[('starter', 'Starter'), ('professional', 'Professional'), ('enterprise', 'Enterprise')], max_length=50, unique=True)),
                ('description', models.TextField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('max_students', models.IntegerField()),
                ('max_teachers', models.IntegerField()),
                ('max_classes', models.IntegerField()),
                ('features', models.JSONField(default=list)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['price'],
            },
        ),
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('phone', models.CharField(max_length=20)),
                ('address', models.TextField()),
                ('city', models.CharField(max_length=100)),
                ('state', models.CharField(max_length=100)),
                ('country', models.CharField(max_length=100)),
                ('postal_code', models.CharField(max_length=20)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='schools/logos/')),
                ('logo_url', models.URLField(blank=True, help_text='Supabase URL for school logo', max_length=500, null=True)),
                ('website', models.URLField(blank=True)),
                ('primary_color', models.CharField(default='#0a0a0a', help_text='Primary brand color (hex format #RRGGBB)', max_length=7)),
                ('secondary_color', models.CharField(default='#008484', help_text='Secondary brand color (hex format #RRGGBB)', max_length=7)),
                ('sidebar_color', models.CharField(default='#209090', help_text='Sidebar accent color (hex format #RRGGBB)', max_length=7)),
                ('status', models.CharField(choices=[('active', 'Active'), ('suspended', 'Suspended'), ('inactive', 'Inactive')], default='active', max_length=20)),
                ('subscription_start', models.DateField(auto_now_add=True)),
                ('subscription_end', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='schools.plan')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['name'], name='schools_sch_name_e14eab_idx'), models.Index(fields=['status'], name='schools_sch_status_8f17ba_idx')],
            },
        ),
        migrations.CreateModel(
            name='Announcement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('audience', models.CharField(choices=[('all', 'All'), ('students', 'Students'), ('teachers', 'Teachers'), ('parents', 'Parents'), ('staff', 'Staff')], default='all', max_length=20)),
                ('priority', models.CharField(choices=[('normal', 'Normal'), ('urgent', 'Urgent'), ('critical', 'Critical')], default='normal', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='users.user')),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='schools.school')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['school', '-created_at'], name='schools_ann_school__8ae37b_idx'), models.Index(fields=['priority'], name='schools_ann_priorit_7f0c6a_idx')],
            },
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('cancelled', 'Cancelled')], default='active', max_length=20)),
                ('start_date', models.DateField(auto_now_add=True)),
                ('end_date', models.DateField()),
                ('auto_renew', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='schools.plan')),
                ('school', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to='schools.school')),
            ],
        ),
    ]
