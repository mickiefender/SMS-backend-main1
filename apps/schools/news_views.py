from django.db import models as django_models
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from core.permissions import IsSchoolAdminOrHigher, CanManageNews
from apps.schools.news_models import News
from apps.schools.news_serializer import NewsSerializer, NewsListSerializer


class NewsViewSet(viewsets.ModelViewSet):
    """
    CRUD for school news.
    - School admins create/update/delete news for their school.
    - Banner upload endpoint: POST /api/schools/news/{id}/upload_banner/
    - Banners endpoint: GET /api/schools/news/banners/ (any authenticated user)
    """
    serializer_class = NewsSerializer
    permission_classes = [permissions.IsAuthenticated, CanManageNews]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        """Allow any authenticated user to access the banners endpoint."""
        if self.action == 'banners':
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == 'list':
            return NewsListSerializer
        return NewsSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == 'super_admin':
            return News.objects.all()
        if user.role in ('student', 'teacher', 'parent'):
            school_id = getattr(user, 'school_id', None)
            if school_id:
                return News.objects.filter(
                    school_id=school_id,
                    is_published=True,
                ).filter(
                    django_models.Q(audience='all') | django_models.Q(audience=user.role + 's')
                )
            return News.objects.none()
        if hasattr(user, 'school') and user.school:
            return News.objects.filter(school=user.school)
        return News.objects.none()

    def perform_create(self, serializer):
        extra = {'school': self.request.user.school, 'created_by': self.request.user}
        if serializer.validated_data.get('is_published', True):
            extra['published_at'] = timezone.now()
        serializer.save(**extra)

    def perform_update(self, serializer):
        instance = self.get_object()
        if not instance.is_published and serializer.validated_data.get('is_published', True):
            serializer.save(published_at=timezone.now())
        else:
            serializer.save()

    @action(
        detail=True,
        methods=['post'],
        url_path='upload-banner',
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_banner(self, request, pk=None):
        """Upload a banner image to Supabase and attach it to a news item."""
        news_item = self.get_object()

        banner_file = request.FILES.get('banner')
        if not banner_file:
            return Response({'error': 'No banner file provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.storage.supabase_service import SupabaseStorageService
            supabase = SupabaseStorageService()

            # Upload to news-banners bucket
            file_path, public_url = supabase.upload_news_banner(
                file_obj=banner_file,
                school_id=news_item.school_id,
                news_id=news_item.id,
            )

            news_item.banner_image_url = public_url
            news_item.save(update_fields=['banner_image_url', 'updated_at'])

            serializer = self.get_serializer(news_item)
            return Response({
                'message': 'Banner uploaded successfully',
                'banner_image_url': public_url,
                'news': serializer.data,
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            # Configuration issues (missing env vars)
            return Response(
                {'error': f'Supabase configuration error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Upload failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['get'])
    def banners(self, request):
        """Return only news items marked as banners (for dashboard carousels)."""
        user = request.user
        school_id = getattr(user, 'school_id', None)
        if not school_id:
            return Response({'error': 'School not found'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = News.objects.filter(
            school_id=school_id,
            is_published=True,
            is_banner=True,
        ).order_by('-created_at')[:10]

        serializer = self.get_serializer(queryset, many=True)
        return Response({'results': serializer.data}, status=status.HTTP_200_OK)
