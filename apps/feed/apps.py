from django.apps import AppConfig


class FeedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.feed'
    verbose_name = 'Alara Learning Feed'

    def ready(self):
        import apps.feed.signals  # noqa: F401
