"""
Unit tests for the Alara Learning Feed.
"""
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.feed import models
from apps.feed.services.lesson_service import LessonService
from apps.feed.services.recommendation_service import RecommendationService
from apps.feed.services.analytics_service import AnalyticsService
from apps.feed.services.moderation_service import ModerationService
from apps.schools.models import School

User = get_user_model()


class FeedModelsTest(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Test School', email='test@school.edu', phone='123',
            address='A', city='C', state='S', country='Ghana', postal_code='00233'
        )
        self.teacher = User.objects.create_user(
            email='teacher@school.edu', username='teacher', password='pass',
            first_name='T', last_name='Eacher', role='teacher', school=self.school
        )
        self.student = User.objects.create_user(
            email='student@school.edu', username='student', password='pass',
            first_name='S', last_name='Tudent', role='student', school=self.school
        )
        self.level = models.FeedAcademicLevel.objects.create(name='Primary', slug='primary')
        self.class_obj = models.FeedAcademicClass.objects.create(
            level=self.level, name='Primary 5', slug='primary-5'
        )
        self.subject = models.FeedSubject.objects.create(name='Mathematics', slug='mathematics')
        self.lesson = models.FeedLesson.objects.create(
            title='Basic Algebra',
            teacher=self.teacher,
            school=self.school,
            level=self.level,
            class_obj=self.class_obj,
            subject=self.subject,
            visibility='public',
            status='approved',
            published_at='2024-01-01T00:00:00Z',
        )

    def test_lesson_string_representation(self):
        self.assertEqual(str(self.lesson), 'Basic Algebra')

    def test_visible_lessons_for_guest(self):
        qs = LessonService.can_view_lesson(self.lesson, None)
        self.assertTrue(qs)

    def test_school_only_not_visible_to_guest(self):
        self.lesson.visibility = 'school_only'
        self.lesson.save()
        self.assertFalse(LessonService.can_view_lesson(self.lesson, None))

    def test_school_only_visible_to_same_school_student(self):
        self.lesson.visibility = 'school_only'
        self.lesson.save()
        self.assertTrue(LessonService.can_view_lesson(self.lesson, self.student))

    def test_like_toggle(self):
        models.FeedLike.objects.create(user=self.student, lesson=self.lesson)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.like_count, 1)
        models.FeedLike.objects.filter(user=self.student, lesson=self.lesson).delete()
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.like_count, 0)

    def test_follow_teacher(self):
        relation = models.TeacherFollower.objects.create(user=self.student, teacher=self.teacher)
        self.assertTrue(
            models.TeacherFollower.objects.filter(user=self.student, teacher=self.teacher).exists()
        )


class FeedServiceTest(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Test School', email='svc@school.edu', phone='123',
            address='A', city='C', state='S', country='Ghana', postal_code='00233'
        )
        self.teacher = User.objects.create_user(
            email='teacher2@school.edu', username='teacher2', password='pass',
            role='teacher', school=self.school
        )
        self.student = User.objects.create_user(
            email='student2@school.edu', username='student2', password='pass',
            role='student', school=self.school
        )
        self.level = models.FeedAcademicLevel.objects.create(name='JHS', slug='jhs')
        self.subject = models.FeedSubject.objects.create(name='Science', slug='science')
        self.lesson = models.FeedLesson.objects.create(
            title='Photosynthesis',
            teacher=self.teacher,
            school=self.school,
            level=self.level,
            subject=self.subject,
            visibility='public',
            status='approved',
            published_at='2024-01-01T00:00:00Z',
        )

    def test_guest_trending_includes_public_lesson(self):
        qs = RecommendationService.get_guest_recommendations('trending')
        self.assertIn(self.lesson.id, list(qs.values_list('id', flat=True)))

    def test_personalized_recommendations_match_preferred_subject(self):
        profile, _ = models.LearningProfile.objects.get_or_create(user=self.student)
        profile.preferred_level = self.level
        profile.save()
        profile.preferred_subjects.add(self.subject)

        qs = RecommendationService.get_recommendations_for_user(self.student)
        ids = list(qs.values_list('id', flat=True))
        self.assertIn(self.lesson.id, ids)

    def test_analytics_view_increments(self):
        AnalyticsService.track_view(self.lesson, self.student)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.view_count, 1)
        analytics = models.LessonAnalytics.objects.get(lesson=self.lesson)
        self.assertEqual(analytics.views, 1)

    def test_moderation_suspends_lesson(self):
        admin = User.objects.create_user(
            email='admin@school.edu', username='admin', password='pass',
            role='school_admin', school=self.school
        )
        ModerationService.suspend_lesson(self.lesson, admin, reason='test')
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, 'suspended')
        self.assertEqual(self.lesson.visibility, 'suspended')


class FeedAPITest(APITestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='API School', email='api@school.edu', phone='123',
            address='A', city='C', state='S', country='Ghana', postal_code='00233'
        )
        self.teacher = User.objects.create_user(
            email='apiteacher@school.edu', username='apiteacher', password='pass',
            role='teacher', school=self.school
        )
        self.student = User.objects.create_user(
            email='apistudent@school.edu', username='apistudent', password='pass',
            role='student', school=self.school
        )
        self.level = models.FeedAcademicLevel.objects.create(name='SHS', slug='shs')
        self.subject = models.FeedSubject.objects.create(name='ICT', slug='ict')
        self.lesson = models.FeedLesson.objects.create(
            title='Intro to Python',
            teacher=self.teacher,
            school=self.school,
            level=self.level,
            subject=self.subject,
            visibility='public',
            status='approved',
            published_at='2024-01-01T00:00:00Z',
        )
        self.client = APIClient()

    def test_guest_can_browse_feed(self):
        url = reverse('feed')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)

    def test_guest_cannot_like(self):
        url = reverse('feed-lesson-like', kwargs={'pk': self.lesson.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_can_like_and_unlike(self):
        self.client.force_authenticate(user=self.student)
        url = reverse('feed-lesson-like', kwargs={'pk': self.lesson.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['liked'])
        response = self.client.post(url)
        self.assertFalse(response.data['liked'])

    def test_teacher_can_create_lesson(self):
        self.client.force_authenticate(user=self.teacher)
        url = reverse('feed-lesson-list')
        data = {
            'title': 'New Lesson',
            'description': 'Lesson description',
            'visibility': 'public',
            'status': 'pending_review',
            'level': self.level.id,
            'subject': self.subject.id,
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(models.FeedLesson.objects.filter(title='New Lesson').count(), 1)

    def test_student_cannot_create_lesson(self):
        self.client.force_authenticate(user=self.student)
        url = reverse('feed-lesson-list')
        response = self.client.post(url, {'title': 'Hack'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_endpoint(self):
        url = reverse('feed-search')
        response = self.client.get(url, {'q': 'Python'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
