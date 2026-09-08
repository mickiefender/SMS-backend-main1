from django.conf import settings
from django.db import models


class ChatSession(models.Model):
    id = models.CharField(max_length=120, primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_chat_sessions',
    )
    title = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    created_at = models.BigIntegerField()
    updated_at = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'ai_chat_sessions'
        ordering = ['-updated_at']
