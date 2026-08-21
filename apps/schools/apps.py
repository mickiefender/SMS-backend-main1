from django.apps import AppConfig


class SchoolsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.schools'

    def ready(self):
        from apps.schools.signals import register_signal_handlers
        register_signal_handlers()
