"""Celery configuration for school management system"""
import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('school_management')

# Load config from Django settings with CELERY namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered Django apps
app.autodiscover_tasks()

# ─── Celery Beat Schedule ─────────────────────────────────────────
app.conf.beat_schedule = {
    # Recalculate trending scores every 30 minutes
    'recalculate-trending-scores': {
        'task': 'apps.feed.tasks.recalculate_trending_scores',
        'schedule': 1800.0,  # every 30 minutes
    },
    # Daily interest score decay at 3:00 AM UTC
    'decay-interest-scores': {
        'task': 'apps.feed.tasks.decay_interest_scores',
        'schedule': crontab(hour=3, minute=0),
    },
    # Refresh aggregate watch metrics every hour
    'aggregate-watch-metrics': {
        'task': 'apps.feed.tasks.aggregate_watch_metrics',
        'schedule': 3600.0,
    },
    # Aggregate daily analytics at midnight
    'aggregate-daily-analytics': {
        'task': 'apps.feed.tasks.aggregate_daily_analytics',
        'schedule': crontab(hour=0, minute=0),
    },
    # Clear stale guest feed caches every 15 minutes
    'clear-stale-feed-caches': {
        'task': 'apps.feed.tasks.clear_stale_feed_caches',
        'schedule': 900.0,
    },
    # Invalidate expired recommendation caches every hour
    'invalidate-expired-recommendation-cache': {
        'task': 'apps.feed.tasks.invalidate_expired_recommendation_cache',
        'schedule': 3600.0,
    },
    # ─── Notifications ──────────────────────────────────────────────
    # Send assignment and fee reminders every 6 hours
    'send-scheduled-reminders': {
        'task': 'apps.notifications.tasks.send_scheduled_reminders',
        'schedule': 21600.0,  # every 6 hours
    },
    # Clean stale FCM devices daily at 4 AM
    'clean-invalid-devices': {
        'task': 'apps.notifications.tasks.clean_invalid_devices',
        'schedule': crontab(hour=4, minute=0),
    },
    # Daily learning reminders — runs every hour so we can match each
    # user's configured preferred reminder time (daily_reminder_time).
    # The task itself only fires for users whose configured hour matches
    # the current hour and who haven't already received one today.
    'send-daily-learning-reminders': {
        'task': 'apps.notifications.tasks.send_daily_learning_reminders',
        'schedule': 3600.0,
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
