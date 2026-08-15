"""
Super Admin lesson-metadata management endpoints.

These endpoints let the super admin (and school admins) create, edit, list
and delete the reference data used by the teacher upload flow:

  - Academic levels & classes
  - Subjects
  - Content types
  - Difficulty levels
  - Curricula
  - Learning objectives
  - Tags
  - Visibility scopes

Mutating actions are restricted to 'super_admin' / 'school_admin' roles.
Read-only access (GET) is open to any authenticated user so the mobile app
can fetch the live lists the same way it fetches levels/classes/subjects.

DELETE protection: a metadata row that is still referenced by lessons /
classes is not hard-deleted; it is soft-deleted via is_active=False so
historical feed content keeps working. Hard delete is available via
`?hard=true` only when the row has no references.
"""
from django.utils.text import slugify
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.feed import models, serializers
from core.permissions import IsSuperAdmin


def _make_unique_slug(model, name, exclude_pk=None):
    """Generate a unique slug for a model with a `slug` field."""
    base = slugify(name) or 'item'
    slug = base
    suffix = 1
    qs = model.objects.filter(slug=slug)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    while qs.exists():
        suffix += 1
        slug = f'{base}-{suffix}'
    return slug


class SafeMetadataMixin:
    """
    Shared behaviour for metadata viewsets:
      - Auto-generate unique slugs when not provided.
      - Prevent hard deletion of rows still referenced by feed lessons.
    """

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        data = serializer.validated_data
        if 'slug' not in data or not data.get('slug'):
            data['slug'] = _make_unique_slug(
                serializer.Meta.model, data.get('name') or ''
            )
        serializer.save()

    def perform_update(self, serializer):
        data = serializer.validated_data
        if 'slug' not in data or not data.get('slug'):
            data['slug'] = _make_unique_slug(
                serializer.Meta.model,
                data.get('name') or serializer.instance.name,
                exclude_pk=serializer.instance.pk,
            )
        serializer.save()

    def _referencing_querysets(self, instance):
        """Return (label, queryset) pairs of records referencing this row."""
        raise NotImplementedError

    def _soft_delete(self, instance):
        if hasattr(instance, 'is_active'):
            instance.is_active = False
            instance.save(update_fields=['is_active'])
            return True
        return False

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        hard = request.query_params.get('hard') == 'true'

        referencing = []
        for label, qs in self._referencing_querysets(instance):
            if qs.exists():
                referencing.append(label)

        if referencing and not hard:
            if self._soft_delete(instance):
                return Response({
                    'detail': (
                        f'"{instance.name}" is still used by {len(referencing)} '
                        f'referencing record(s): {" ".join(referencing)}. '
                        'It was deactivated instead of deleted. Deactivated items '
                        'stop showing for new uploads but keep existing feeds intact.'
                    ),
                    'deactivated': True,
                }, status=status.HTTP_200_OK)
            raise ValidationError(
                {'detail': 'This item is in use and cannot be deleted.'}
            )

        if referencing and hard:
            raise ValidationError(
                {'detail': (
                    f'Cannot hard-delete: still referenced by '
                    f'{" ".join(referencing)}.'
                )}
            )

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Individual viewsets
# ---------------------------------------------------------------------------

class AdminAcademicLevelViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedAcademicLevelSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedAcademicLevel.objects.all().order_by('order', 'name')

    def _referencing_querysets(self, instance):
        return [
            ('classes', models.FeedAcademicClass.objects.filter(level_id=instance.pk)),
            ('lessons', models.FeedLesson.objects.filter(level_id=instance.pk)),
            ('learning_profiles', models.LearningProfile.objects.filter(preferred_level_id=instance.pk)),
            ('guest_learners', models.GuestLearner.objects.filter(level_id=instance.pk)),
        ]


class AdminAcademicClassViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedAcademicClassSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedAcademicClass.objects.all().select_related('level')

    def _referencing_querysets(self, instance):
        return [
            ('lessons', models.FeedLesson.objects.filter(class_obj_id=instance.pk)),
            ('learning_profiles', models.LearningProfile.objects.filter(preferred_class_id=instance.pk)),
            ('guest_learners', models.GuestLearner.objects.filter(class_obj_id=instance.pk)),
        ]


class AdminSubjectViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedSubjectSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedSubject.objects.all().order_by('name')

    def _referencing_querysets(self, instance):
        return [
            ('lessons', models.FeedLesson.objects.filter(subject_id=instance.pk)),
            ('learning_profiles', models.LearningProfile.objects.filter(preferred_subjects=instance.pk)),
            ('guest_learners', models.GuestLearner.objects.filter(subjects=instance.pk)),
        ]


class AdminContentTypeViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedContentTypeSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedContentType.objects.all().order_by('name')

    def _referencing_querysets(self, instance):
        return [('lessons', models.FeedLesson.objects.filter(content_type_id=instance.pk))]


class AdminDifficultyLevelViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedDifficultyLevelSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedDifficultyLevel.objects.all().order_by('order', 'name')

    def _referencing_querysets(self, instance):
        return [('lessons', models.FeedLesson.objects.filter(difficulty_level_id=instance.pk))]


class AdminCurriculumViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedCurriculumSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedCurriculum.objects.all().order_by('name')

    def _referencing_querysets(self, instance):
        return [('lessons', models.FeedLesson.objects.filter(curriculum_id=instance.pk))]


class AdminLearningObjectiveViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedLearningObjectiveSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedLearningObjective.objects.all().order_by('name')

    def _referencing_querysets(self, instance):
        return [('lessons', models.FeedLesson.objects.filter(learning_objective_id=instance.pk))]


class AdminTagViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedTagSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedTag.objects.all().order_by('-usage_count', 'name')

    def _referencing_querysets(self, instance):
        return [('lessons', models.FeedLesson.objects.filter(tags=instance.pk))]


class AdminVisibilityScopeViewSet(SafeMetadataMixin, viewsets.ModelViewSet):
    serializer_class = serializers.FeedVisibilityScopeSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        return models.FeedVisibilityScope.objects.all().order_by('name')

    def _referencing_querysets(self, instance):
        return []
