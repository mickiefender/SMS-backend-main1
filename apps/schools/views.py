from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from core.permissions import IsSuperAdmin, IsSchoolAdminOrHigher
from core.cache import DashboardCache
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
        if hasattr(self.request.user, 'school') and self.request.user.school:
            return School.objects.filter(id=self.request.user.school.id)
        return School.objects.none()
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """
        Get dashboard statistics with caching
        """
        school_id = request.user.school_id if hasattr(request.user, 'school_id') and request.user.school else None
        
        if not school_id:
            return Response({'error': 'School not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Try to get from cache first
        cached_stats = DashboardCache.get_stats(school_id)
        if cached_stats:
            return Response({
                'data': cached_stats,
                'cached': True
            })
        
        # Calculate fresh stats
        now = timezone.now()
        
        # Student count
        students_count = User.objects.filter(role='student', school_id=school_id).count()
        
        # Teacher count
        teachers_count = User.objects.filter(role='teacher', school_id=school_id).count()
        
        # Staff/Parents count (other users)
        parents_count = User.objects.filter(role='parent', school_id=school_id).count()
        
        # Get total revenue from billing (ManualPayment)
        try:
            from apps.billing.models import ManualPayment
            total_earnings = ManualPayment.objects.filter(
                school_id=school_id
            ).aggregate(total=Sum('amount'))['total'] or 0
        except Exception:
            total_earnings = 0
        
        stats = {
            'students': students_count,
            'teachers': teachers_count,
            'parents': parents_count,
            'earnings': float(total_earnings),
            'calculated_at': now.isoformat(),
        }
        
        # Cache the stats (5 minutes)
        DashboardCache.cache_stats(school_id, stats)
        
        return Response({
            'data': stats,
            'cached': False
        })
    
    @action(detail=False, methods=['post'])
    def invalidate_cache(self, request):
        """
        Manually invalidate dashboard cache for a school
        """
        school_id = request.user.school_id if hasattr(request.user, 'school_id') and request.user.school else None
        
        if not school_id:
            return Response({'error': 'School not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        DashboardCache.invalidate_stats(school_id)
        
        return Response({'message': 'Cache invalidated successfully'})

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsSuperAdmin])
    def super_admin_usage(self, request):
        from apps.billing.models import OnlinePayment, ManualPayment

        schools = School.objects.select_related('plan').all()
        data = []
        for school in schools:
            students_count = User.objects.filter(school=school, role='student').count()
            teachers_count = User.objects.filter(school=school, role='teacher').count()
            storage_used_mb = 0
            total_revenue = (
                (ManualPayment.objects.filter(school=school).aggregate(total=Sum('amount'))['total'] or 0) +
                (OnlinePayment.objects.filter(school=school, status='success').aggregate(total=Sum('amount'))['total'] or 0)
            )
            data.append({
                'school_id': school.id,
                'school_name': school.name,
                'plan': school.plan.name if school.plan else None,
                'students': students_count,
                'teachers': teachers_count,
                'storage_used_mb': float(storage_used_mb),
                'revenue': float(total_revenue),
                'status': school.status,
            })

        return Response({'results': data})

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsSuperAdmin])
    def super_admin_analytics(self, request):
        from apps.billing.models import OnlinePayment, ManualPayment

        now = timezone.now()
        last_30_days = now - timedelta(days=30)

        total_schools = School.objects.count()
        total_users = User.objects.count()
        active_tenants = School.objects.filter(status='active').count()
        inactive_tenants = School.objects.exclude(status='active').count()

        manual_total = ManualPayment.objects.aggregate(total=Sum('amount'))['total'] or 0
        online_total = OnlinePayment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or 0
        revenue_total = manual_total + online_total

        new_schools_30 = School.objects.filter(created_at__gte=last_30_days).count()
        new_users_30 = User.objects.filter(created_at__gte=last_30_days).count()

        growth_chart = []
        for i in range(5, -1, -1):
            start = now - timedelta(days=(i + 1) * 30)
            end = now - timedelta(days=i * 30)
            growth_chart.append({
                'period': f"{start.strftime('%b %Y')}",
                'schools': School.objects.filter(created_at__gte=start, created_at__lt=end).count(),
                'users': User.objects.filter(created_at__gte=start, created_at__lt=end).count(),
                'revenue': float(
                    (ManualPayment.objects.filter(created_at__gte=start, created_at__lt=end).aggregate(total=Sum('amount'))['total'] or 0) +
                    (OnlinePayment.objects.filter(created_at__gte=start, created_at__lt=end, status='success').aggregate(total=Sum('amount'))['total'] or 0)
                )
            })

        return Response({
            'kpis': {
                'total_schools': total_schools,
                'total_users': total_users,
                'revenue_total': float(revenue_total),
                'active_tenants': active_tenants,
                'inactive_tenants': inactive_tenants,
                'new_schools_30_days': new_schools_30,
                'new_users_30_days': new_users_30,
            },
            'growth_chart': growth_chart
        })
    
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
    
    @action(detail=False, methods=['post'], permission_classes=[IsSchoolAdminOrHigher])
    def upload_logo(self, request):
        """
        Upload school logo to Supabase storage
        """
        from apps.storage.supabase_service import SupabaseStorageService
        
        # Get the school - for school admin, use their own school
        if request.user.role == 'school_admin':
            school = request.user.school
        else:
            school_id = request.data.get('school_id')
            if not school_id:
                return Response({'error': 'school_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get the logo file
        logo_file = request.FILES.get('logo')
        if not logo_file:
            return Response({'error': 'No logo file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Upload to Supabase
            supabase_service = SupabaseStorageService()
            file_path, public_url = supabase_service.upload_school_logo(
                file_obj=logo_file,
                school_id=school.id,
                school_name=school.name
            )
            
            # Update school record with logo URL
            school.logo_url = public_url
            school.save()
            
            serializer = self.get_serializer(school)
            return Response({
                'message': 'Logo uploaded successfully',
                'logo_url': public_url,
                'school': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
