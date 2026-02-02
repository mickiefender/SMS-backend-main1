from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from apps.academics.models import Subject, Syllabus, SyllabusTopic, School

User = get_user_model()

class AcademicsAPITest(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Test School')
        self.school_admin = User.objects.create_user(
            email='admin@test.com',
            password='password',
            role='school_admin',
            school=self.school
        )
        self.teacher = User.objects.create_user(
            email='teacher@test.com',
            password='password',
            role='teacher',
            school=self.school
        )
        self.subject = Subject.objects.create(
            name='Test Subject',
            school=self.school
        )
        self.syllabus = Syllabus.objects.create(
            subject=self.subject,
            title='Test Syllabus'
        )

    def test_create_syllabus(self):
        self.client.force_authenticate(user=self.school_admin)
        url = reverse('syllabus-list')
        data = {
            'subject': self.subject.pk,
            'title': 'New Syllabus'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Syllabus.objects.count(), 2)

    def test_create_syllabus_topic(self):
        self.client.force_authenticate(user=self.teacher)
        url = reverse('syllabus-topic-list')
        data = {
            'syllabus': self.syllabus.pk,
            'title': 'New Topic',
            'order': 1
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SyllabusTopic.objects.count(), 1)

    def test_get_syllabus(self):
        self.client.force_authenticate(user=self.teacher)
        url = reverse('syllabus-detail', kwargs={'pk': self.syllabus.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Syllabus')

    def test_get_syllabus_topics(self):
        self.client.force_authenticate(user=self.teacher)
        SyllabusTopic.objects.create(
            syllabus=self.syllabus,
            title='Topic 1',
            order=1
        )
        SyllabusTopic.objects.create(
            syllabus=self.syllabus,
            title='Topic 2',
            order=2
        )
        url = reverse('syllabus-detail', kwargs={'pk': self.syllabus.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['topics']), 2)
