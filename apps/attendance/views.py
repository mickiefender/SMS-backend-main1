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
    
    @action(detail=False, methods=['get'])
    def student_report(self, request):
        """Get attendance report for a student"""
        student_id = request.query_params.get('student_id')
        if request.user.role == 'student':
            attendances = Attendance.objects.filter(student=request.user)
        else:
            attendances = Attendance.objects.filter(student_id=student_id, class_obj__school=request.user.school)
        
        total = attendances.count()
        present = attendances.filter(status='present').count()
        percentage = (present / total * 100) if total > 0 else 0
        
        return Response({
            'total': total,
            'present': present,
            'absent': attendances.filter(status='absent').count(),
            'percentage': percentage,
            'records': AttendanceSerializer(attendances, many=True).data
        })
