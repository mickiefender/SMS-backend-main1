"""Django app initialization with Celery"""
import django
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Import Celery app when Django starts
        from .celery import app as celery_app
        __all__ = ('celery_app',)
