"""
Management command to seed lesson metadata reference tables.

Usage:
    python manage.py seed_lesson_metadata
"""
from django.core.management.base import BaseCommand
from apps.feed.models import (
    FeedContentType,
    FeedDifficultyLevel,
    FeedCurriculum,
    FeedLearningObjective,
    FeedVisibilityScope,
)


class Command(BaseCommand):
    help = 'Seed lesson metadata reference tables'

    def handle(self, *args, **options):
        self._seed_content_types()
        self._seed_difficulty_levels()
        self._seed_curricula()
        self._seed_learning_objectives()
        self._seed_visibility_scopes()

        self.stdout.write(self.style.SUCCESS('Successfully seeded all lesson metadata reference tables.'))

    def _seed_content_types(self):
        items = [
            ('Lesson Explanation', 'lesson_explanation'),
            ('Exam Preparation', 'exam_preparation'),
            ('Homework Help', 'homework_help'),
            ('Study Tips', 'study_tips'),
            ('Classroom Activity', 'classroom_activity'),
            ('School Announcement', 'school_announcement'),
            ('Teacher Training', 'teacher_training'),
            ('Motivation', 'motivation'),
            ('Educational Entertainment', 'educational_entertainment'),
        ]
        created = 0
        for name, slug in items:
            _, is_new = FeedContentType.objects.get_or_create(
                slug=slug, defaults={'name': name}
            )
            if is_new:
                created += 1
        self.stdout.write(f'  Content types: {created} created, {len(items) - created} already exist')

    def _seed_difficulty_levels(self):
        items = [
            ('Beginner', 'beginner', 0),
            ('Intermediate', 'intermediate', 1),
            ('Advanced', 'advanced', 2),
        ]
        created = 0
        for name, slug, order in items:
            _, is_new = FeedDifficultyLevel.objects.get_or_create(
                slug=slug, defaults={'name': name, 'order': order}
            )
            if is_new:
                created += 1
        self.stdout.write(f'  Difficulty levels: {created} created, {len(items) - created} already exist')

    def _seed_curricula(self):
        items = [
            ('GES Curriculum', 'ges_curriculum'),
            ('NaCCA', 'nacca'),
            ('BECE Preparation', 'bece_preparation'),
            ('Cambridge', 'cambridge'),
            ('Other', 'other'),
        ]
        created = 0
        for name, slug in items:
            _, is_new = FeedCurriculum.objects.get_or_create(
                slug=slug, defaults={'name': name}
            )
            if is_new:
                created += 1
        self.stdout.write(f'  Curricula: {created} created, {len(items) - created} already exist')

    def _seed_learning_objectives(self):
        items = [
            ('Introduce a New Concept', 'introduce_new_concept'),
            ('Revision', 'revision'),
            ('Practice Questions', 'practice_questions'),
            ('Exam Preparation', 'exam_preparation'),
            ('Demonstration', 'demonstration'),
            ('Motivation', 'motivation'),
        ]
        created = 0
        for name, slug in items:
            _, is_new = FeedLearningObjective.objects.get_or_create(
                slug=slug, defaults={'name': name}
            )
            if is_new:
                created += 1
        self.stdout.write(f'  Learning objectives: {created} created, {len(items) - created} already exist')

    def _seed_visibility_scopes(self):
        items = [
            ('Only My School', 'only_my_school', 'Visible only to users within the same school.'),
            ('Schools in My Region', 'schools_in_region', 'Visible to users in schools within the same region.'),
            ('Public Feed', 'public_feed', 'Visible to all users on the platform.'),
        ]
        created = 0
        for name, slug, desc in items:
            _, is_new = FeedVisibilityScope.objects.get_or_create(
                slug=slug, defaults={'name': name, 'description': desc}
            )
            if is_new:
                created += 1
        self.stdout.write(f'  Visibility scopes: {created} created, {len(items) - created} already exist')
