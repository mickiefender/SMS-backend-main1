from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.compliance'
    verbose_name = 'School Compliance'

    def ready(self):
        # Register the School post_save hook that creates a compliance profile
        # the moment a school account is created by the Super Admin.
        from apps.compliance.signals import register_signal_handlers
        register_signal_handlers()
