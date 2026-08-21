from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.attendance'

    def ready(self):
        from apps.attendance.signals import register_signal_handlers
        register_signal_handlers()
