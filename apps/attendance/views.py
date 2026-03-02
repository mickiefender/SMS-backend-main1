from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsTeacher, IsSchoolAdminOrTeacher
from apps.attendance.models import Attendance
from apps.attendance.serializers import AttendanceSerializer


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return Attendance.objects.all()
        elif self.request.user.role == 'teacher':
            return Attendance.objects.filter(teacher=self.request.user)
        elif self.request.user.role == 'student':
            return Attendance.objects.filter(student=self.request.user)
        return Attendance.objects.filter(class_obj__school=self.request.user.school)
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated()]
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsTeacher])
    def bulk_mark(self, request):
        """Bulk mark attendance for multiple students"""
        attendances = request.data.get('attendances', [])
        created = 0
        errors = []
        for att_data in attendances:
            serializer = self.get_serializer(data=att_data)
            if serializer.is_valid():
                serializer.save(teacher=request.user)
                created += 1
            else:
                errors.append({
                    'data': att_data,
                    'errors': serializer.errors
                })
        return Response({
            'created': created,
            'errors': errors if errors else None
        }, status=status.HTTP_201_CREATED if created > 0 else status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def student_report(self, request):
        """Get attendance report for a student"""
        student_id = request.query_params.get('student_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Students can view their own attendance
        if request.user.role == 'student':
            attendances = Attendance.objects.filter(student=request.user)
        # Teachers and school admins can view student attendance
        elif request.user.role in ['teacher', 'school_admin'] or hasattr(request.user, 'school'):
            if student_id:
                attendances = Attendance.objects.filter(student_id=student_id)
                # Additional school filter if user has a school
                if hasattr(request.user, 'school') and request.user.school:
                    attendances = attendances.filter(class_obj__school=request.user.school)
            else:
                attendances = Attendance.objects.none()
        # Super admin can view all
        elif request.user.role == 'super_admin':
            if student_id:
                attendances = Attendance.objects.filter(student_id=student_id)
            else:
                attendances = Attendance.objects.all()
        else:
            attendances = Attendance.objects.none()
        
        # Filter by date range if provided
        if start_date:
            attendances = attendances.filter(date__gte=start_date)
        if end_date:
            attendances = attendances.filter(date__lte=end_date)
        
        total = attendances.count()
        present = attendances.filter(status='present').count()
        late = attendances.filter(status='late').count()
        absent = attendances.filter(status='absent').count()
        excused = attendances.filter(status='excused').count()
        percentage = (present / total * 100) if total > 0 else 0
        
        # Group by date for recent records
        recent_records = attendances.order_by('-date')[:30]
        
        return Response({
            'total_days': total,
            'present_days': present,
            'absent_days': absent,
            'late_days': late,
            'excused_days': excused,
            'presence_percentage': percentage,
            'records': AttendanceSerializer(recent_records, many=True).data
        })
