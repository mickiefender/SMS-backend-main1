from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsSuperAdmin, IsSchoolAdminOrHigher
from apps.schools.models import School, Plan, Subscription, Announcement
from apps.schools.serializers import SchoolSerializer, PlanSerializer, SubscriptionSerializer, AnnouncementSerializer
from apps.users.models import User


class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.filter(is_active=True)
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]


class SchoolViewSet(viewsets.ModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'destroy', 'suspend', 'activate']:
            return [IsSuperAdmin()]
        if self.action in ['update', 'partial_update']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return School.objects.all()
        return School.objects.filter(id=self.request.user.school.id)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school = serializer.save()
        
        # Create school admin user
        admin_password = request.data.get('admin_password', 'SchoolAdmin@123')
        admin_email = request.data.get('admin_email', f"admin@{school.email.split('@')[1]}")
        admin_username = request.data.get('admin_username', f"admin_{school.id}")
        
        try:
            admin_user = User.objects.create_user(
                username=admin_username,
                email=admin_email,
                password=admin_password,
                role='school_admin',
                school=school,
                is_staff=True
            )
            print(f"[v0] School admin created: {admin_email}")
        except Exception as e:
            print(f"[v0] Error creating school admin: {e}")
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def suspend(self, request, pk=None):
        school = self.get_object()
        school.status = 'suspended'
        school.save()
        return Response({'status': 'School suspended'})
    
    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def activate(self, request, pk=None):
        school = self.get_object()
        school.status = 'active'
        school.save()
        return Response({'status': 'School activated'})


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Subscription.objects.all()
        return Subscription.objects.filter(school=self.request.user.school)


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated, IsSchoolAdminOrHigher]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Announcement.objects.all()
        return Announcement.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, school=self.request.user.school)
