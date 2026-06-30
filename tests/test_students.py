from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from apps.students.models import StudentSocialClub, StudentSocialClubMember

User = get_user_model()

class StudentSocialClubAPITest(APITestCase):
    def setUp(self):
        self.school_admin = User.objects.create_user(
            email='admin@test.com',
            password='password',
            role='school_admin'
        )
        self.student = User.objects.create_user(
            email='student@test.com',
            password='password',
            role='student'
        )
        self.club = StudentSocialClub.objects.create(
            name='Test Club',
            description='A club for testing'
        )

    def test_join_club(self):
        self.client.force_authenticate(user=self.student)
        url = reverse('social-club-manage-membership', kwargs={'pk': self.club.pk})
        response = self.client.post(url, {'action': 'join'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StudentSocialClubMember.objects.count(), 1)
        self.assertEqual(StudentSocialClubMember.objects.get().status, 'pending')

    def test_approve_membership(self):
        self.client.force_authenticate(user=self.school_admin)
        member = StudentSocialClubMember.objects.create(
            club=self.club,
            student=self.student,
            status='pending'
        )
        url = reverse('social-club-approve-membership', kwargs={'pk': self.club.pk})
        response = self.client.post(url, {'student_id': self.student.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        member.refresh_from_db()
        self.assertEqual(member.status, 'active')

    def test_get_club_members(self):
        self.client.force_authenticate(user=self.student)
        StudentSocialClubMember.objects.create(
            club=self.club,
            student=self.student,
            status='active'
        )
        url = reverse('social-club-members', kwargs={'pk': self.club.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_get_club_members_by_status(self):
        self.client.force_authenticate(user=self.student)
        StudentSocialClubMember.objects.create(
            club=self.club,
            student=self.student,
            status='active'
        )
        User.objects.create_user(
            email='student2@test.com',
            password='password',
            role='student'
        )
        StudentSocialClubMember.objects.create(
            club=self.club,
            student=User.objects.get(email='student2@test.com'),
            status='pending'
        )
        url = reverse('social-club-members', kwargs={'pk': self.club.pk})
        response = self.client.get(url, {'status': 'active'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
