"""
Management command to seed lesson metadata reference tables.

Usage:
    python manage.py seed_lesson_metadata

Seeds academic levels, classes and subjects (used by the teacher upload
flow), plus content types, difficulty levels, curricula, learning
objectives and visibility scopes. IDs are assigned explicitly to match the
IDs the mobile app sends, so script is idempotent and deterministic across
environments.
"""
from django.core.management.base import BaseCommand
from apps.feed.models import (
    FeedAcademicLevel,
    FeedAcademicClass,
    FeedSubject,
    FeedContentType,
    FeedDifficultyLevel,
    FeedCurriculum,
    FeedLearningObjective,
    FeedVisibilityScope,
)


class Command(BaseCommand):
    help = 'Seed lesson metadata reference tables'

    def handle(self, *args, **options):
        self._seed_academic_levels()
        self._seed_academic_classes()
        self._seed_subjects()
        self._seed_content_types()
        self._seed_difficulty_levels()
        self._seed_curricula()
        self._seed_learning_objectives()
        self._seed_visibility_scopes()

        self.stdout.write(self.style.SUCCESS('Successfully seeded all lesson metadata reference tables.'))

    # ─── Academic levels ──────────────────────────────────────────
    # IDs match the mobile app's level map
    # (nursery=1, kg=2, primary_1=3 .. shs=12, University=13).
    def _seed_academic_levels(self):
        items = [
            (1, 'Nursery', 'nursery', 0),
            (2, 'KG', 'kg', 1),
            (3, 'Primary 1', 'primary_1', 2),
            (4, 'Primary 2', 'primary_2', 3),
            (5, 'Primary 3', 'primary_3', 4),
            (6, 'Primary 4', 'primary_4', 5),
            (7, 'Primary 5', 'primary_5', 6),
            (8, 'Primary 6', 'primary_6', 7),
            (9, 'JHS 1', 'jhs_1', 8),
            (10, 'JHS 2', 'jhs_2', 9),
            (11, 'JHS 3', 'jhs_3', 10),
            (12, 'SHS', 'shs', 11),
            (13, 'University', 'university', 12),
        ]
        created = 0
        for pk, name, slug, order in items:
            FeedAcademicLevel.objects.update_or_create(
                slug=slug,
                defaults={'id': pk, 'name': name, 'order': order},
            )
            created += 1
        self.stdout.write(f'  Academic levels: {created} present')

    # ─── Academic classes ─────────────────────────────────────────
    # One class per level, each linked to its matching level ID and
    # matching the mobile app's class-by-level map (1..13).
    def _seed_academic_classes(self):
        items = [
            (1, 'Nursery', 'nursery', 1),
            (2, 'KG', 'kg', 2),
            (3, 'Primary 1', 'primary_1', 3),
            (4, 'Primary 2', 'primary_2', 4),
            (5, 'Primary 3', 'primary_3', 5),
            (6, 'Primary 4', 'primary_4', 6),
            (7, 'Primary 5', 'primary_5', 7),
            (8, 'Primary 6', 'primary_6', 8),
            (9, 'JHS 1', 'jhs_1', 9),
            (10, 'JHS 2', 'jhs_2', 10),
            (11, 'JHS 3', 'jhs_3', 11),
            (12, 'SHS', 'shs', 12),
            (13, 'University', 'university', 13),
        ]
        created = 0
        for pk, name, slug, level_id in items:
            FeedAcademicClass.objects.update_or_create(
                slug=slug,
                defaults={
                    'id': pk,
                    'name': name,
                    'level_id': level_id,
                    'order': level_id - 1,
                },
            )
            created += 1
        self.stdout.write(f'  Academic classes: {created} present')

    # ─── Subjects ─────────────────────────────────────────────────
    # IDs match the mobile app's subject map
    # (mathematics=1 .. business=12, Other=13).
    def _seed_subjects(self):
        items = [
            (1, 'Mathematics', 'mathematics'),
            (2, 'English Language', 'english_language'),
            (3, 'Science', 'science'),
            (4, 'ICT', 'ict'),
            (5, 'Social Studies', 'social_studies'),
            (6, 'French', 'french'),
            (7, 'Religious Studies', 'religious_studies'),
            (8, 'Creative Arts', 'creative_arts'),
            (9, 'Physics', 'physics'),
            (10, 'Chemistry', 'chemistry'),
            (11, 'Biology', 'biology'),
            (12, 'Business', 'business'),
            (13, 'Other', 'other'),
        ]
        created = 0
        for pk, name, slug in items:
            FeedSubject.objects.update_or_create(
                slug=slug,
                defaults={'id': pk, 'name': name},
            )
            created += 1
        self.stdout.write(f'  Subjects: {created} present')

    # ─── Content types ────────────────────────────────────────────
    # IDs match the mobile app's content type map (1..9).
    def _seed_content_types(self):
        items = [
            (1, 'Lesson Explanation', 'lesson_explanation'),
            (2, 'Exam Preparation', 'exam_preparation'),
            (3, 'Homework Help', 'homework_help'),
            (4, 'Study Tips', 'study_tips'),
            (5, 'Classroom Activity', 'classroom_activity'),
            (6, 'School Announcement', 'school_announcement'),
            (7, 'Teacher Training', 'teacher_training'),
            (8, 'Motivation', 'motivation'),
            (9, 'Educational Entertainment', 'educational_entertainment'),
        ]
        created = 0
        for pk, name, slug in items:
            FeedContentType.objects.update_or_create(
                slug=slug,
                defaults={'id': pk, 'name': name},
            )
            created += 1
        self.stdout.write(f'  Content types: {created} present')

    # ─── Difficulty levels ────────────────────────────────────────
    # IDs match the mobile app's difficulty map (1..3).
    def _seed_difficulty_levels(self):
        items = [
            (1, 'Beginner', 'beginner', 0),
            (2, 'Intermediate', 'intermediate', 1),
            (3, 'Advanced', 'advanced', 2),
        ]
        created = 0
        for pk, name, slug, order in items:
            FeedDifficultyLevel.objects.update_or_create(
                slug=slug,
                defaults={'id': pk, 'name': name, 'order': order},
            )
            created += 1
        self.stdout.write(f'  Difficulty levels: {created} present')

    # ─── Curricula ────────────────────────────────────────────────
    # IDs match the mobile app's curriculum map (1..5).
    def _seed_curricula(self):
        items = [
            (1, 'GES Curriculum', 'ges_curriculum'),
            (2, 'NaCCA', 'nacca'),
            (3, 'BECE Preparation', 'bece_preparation'),
            (4, 'Cambridge', 'cambridge'),
            (5, 'Other', 'other'),
        ]
        created = 0
        for pk, name, slug in items:
            FeedCurriculum.objects.update_or_create(
                slug=slug,
                defaults={'id': pk, 'name': name},
            )
            created += 1
        self.stdout.write(f'  Curricula: {created} present')

    # ─── Learning objectives ──────────────────────────────────────
    # IDs match the mobile app's objective map (1..6).
    def _seed_learning_objectives(self):
        items = [
            (1, 'Introduce a New Concept', 'introduce_new_concept'),
            (2, 'Revision', 'revision'),
            (3, 'Practice Questions', 'practice_questions'),
            (4, 'Exam Preparation', 'exam_preparation'),
            (5, 'Demonstration', 'demonstration'),
            (6, 'Motivation', 'motivation'),
        ]
        created = 0
        for pk, name, slug in items:
            FeedLearningObjective.objects.update_or_create(
                slug=slug,
                defaults={'id': pk, 'name': name},
            )
            created += 1
        self.stdout.write(f'  Learning objectives: {created} present')

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
