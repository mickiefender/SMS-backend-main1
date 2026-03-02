from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
    ]

    operations = [
        # Make picture field optional (for backward compatibility)
        migrations.AlterField(
            model_name='userprofilepicture',
            name='picture',
            field=models.ImageField(blank=True, null=True, upload_to='profile_pictures/'),
        ),
        
        # Add Supabase Storage fields
        migrations.AddField(
            model_name='userprofilepicture',
            name='storage_path',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='userprofilepicture',
            name='storage_url',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofilepicture',
            name='file_size',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofilepicture',
            name='content_type',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='userprofilepicture',
            name='width',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofilepicture',
            name='height',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]

