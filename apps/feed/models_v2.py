"""
Alara Learning Feed — Recommendation & Interaction Models.

These models extend the core feed models to support:
  - Fine-grained user interaction tracking
  - Per-user interest scoring that evolves over time
  - The 70/20/10 blended feed algorithm
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Interaction tracking
# ---------------------------------------------------------------------------

class InteractionType(models.TextChoices):
    IMPRESSION = 'impression', 'Impression'
    WATCH_START = 'watch_start', 'Watch Started'
    WATCH_UPDATE = 'watch_update', 'Watch Progress Update'
    WATCH_COMPLETE = 'watch_complete', 'Watch Completed'
    LIKE = 'like', 'Liked'
    UNLIKE = 'unlike', 'Unliked'
    COMMENT = 'comment', 'Commented'
    SHARE = 'share', 'Shared'
    SAVE = 'save', 'Saved'
    UNSAVE = 'unsave', 'Unsave'
    SKIP = 'skip', 'Skipped'
    FOLLOW_TEACHER = 'follow_teacher', 'Followed Teacher'
    UNFOLLOW_TEACHER = 'unfollow_teacher', 'Unfollowed Teacher'


class UserInteraction(models.Model):
    """
    Every meaningful user action on a lesson is recorded here.

    This is the raw data feed for the interest scoring system.
    Retention: interactions older than 90 days may be archived.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='feed_interactions'
    )
    guest_device_id = models.CharField(
        max_length=255, blank=True, db_index=True,
        help_text="UUID for unauthenticated guest users"
    )
    lesson = models.ForeignKey(
        'feed.FeedLesson', on_delete=models.CASCADE,
        related_name='interactions'
    )
    interaction_type = models.CharField(
        max_length=30, choices=InteractionType.choices
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'feed_userinteraction'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['guest_device_id', '-created_at']),
            models.Index(fields=['lesson', 'interaction_type']),
            models.Index(fields=['-created_at']),
        ]
        verbose_name = 'User Interaction'
        verbose_name_plural = 'User Interactions'

    def __str__(self):
        owner = self.user_id or self.guest_device_id
        return f"Interaction({owner}, {self.interaction_type}, lesson={self.lesson_id})"


# ---------------------------------------------------------------------------
# Interest scores
# ---------------------------------------------------------------------------

class InterestDomain(models.TextChoices):
    SUBJECT = 'subject', 'Subject'
    LEVEL = 'level', 'Academic Level'
    CLASS_OBJ = 'class_obj', 'Academic Class'
    TAG = 'tag', 'Hashtag/Tag'
    TEACHER = 'teacher', 'Teacher'
    CONTENT_TYPE = 'content_type', 'Content Type'
    DIFFICULTY = 'difficulty', 'Difficulty Level'


class UserInterestScore(models.Model):
    """
    A weighted cumulative score for a user's interest in a particular domain
    entity (subject, level, class, tag, or teacher).

    Positive interactions (like, save, watch_complete) increase the score.
    Negative interactions (skip, unlike) decrease it.

    Scores decay over time if not reinforced. Behavioral data gradually
    becomes more important than original onboarding preferences.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='interest_scores'
    )
    guest_device_id = models.CharField(
        max_length=255, blank=True,
        help_text="UUID for unauthenticated guest users"
    )
    interest_domain = models.CharField(
        max_length=20, choices=InterestDomain.choices
    )
    interest_id = models.IntegerField(
        help_text="FK ID of the entity (subject_id, level_id, tag_id, teacher_id, class_obj_id)"
    )

    # Score range: -100 to +100 (capped)
    score = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        validators=[MinValueValidator(-100), MaxValueValidator(100)]
    )

    # Raw counts for analytics
    positive_interactions = models.IntegerField(default=0)
    negative_interactions = models.IntegerField(default=0)

    # Signal that this came from onboarding (decays slower)
    is_onboarding_preference = models.BooleanField(default=False)

    last_interaction_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_userinterestscore'
        unique_together = [
            ['user', 'interest_domain', 'interest_id'],
            ['guest_device_id', 'interest_domain', 'interest_id'],
        ]
        indexes = [
            models.Index(fields=['user', 'interest_domain', '-score']),
            models.Index(fields=['guest_device_id', 'interest_domain', '-score']),
        ]
        verbose_name = 'User Interest Score'
        verbose_name_plural = 'User Interest Scores'

    def __str__(self):
        owner = self.user_id or self.guest_device_id
        return f"Interest({owner}, {self.interest_domain}:{self.interest_id}, score={self.score})"


# ---------------------------------------------------------------------------
# Guest interaction model (backed by a table that also has DB triggers)
# ---------------------------------------------------------------------------

class GuestInteraction(models.Model):
    """
    Lightweight interaction record for guest users, designed to be
    written/read via raw SQL for trigger compatibility.

    Django model exists for migration management; most service-layer
    reads use the GuestLearner model or raw SQL.
    """
    device_id = models.UUIDField(help_text="Client-generated device UUID")
    lesson = models.ForeignKey(
        'feed.FeedLesson', on_delete=models.CASCADE,
        related_name='guest_interactions'
    )
    interaction_type = models.CharField(max_length=30)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feed_guestinteraction'
        indexes = [
            models.Index(fields=['device_id', '-created_at']),
        ]
        verbose_name = 'Guest Interaction'
        verbose_name_plural = 'Guest Interactions'
