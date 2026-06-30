"""
Multi-tenant middleware for isolating data by school
"""
from django.utils.deprecation import MiddlewareMixin
from apps.schools.models import School


class MultiTenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Extract school_id from header or query parameter
        school_id = request.META.get('HTTP_X_SCHOOL_ID') or request.GET.get('school_id')
        
        if school_id:
            try:
                request.school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                request.school = None
        else:
            request.school = None
        
        return None
