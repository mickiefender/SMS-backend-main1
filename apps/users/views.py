from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from django.db import connection, OperationalError, IntegrityError, transaction
from core.permissions import IsSchoolAdminOrHigher
from apps.users.models import User, TeacherProfile, StudentProfile, RolePermission
from apps.academics.models import StudentClass
from apps.users.serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer, AdminStaffCreateSerializer,
    TeacherProfileSerializer, StudentProfileSerializer
)
import time


def ensure_connection():
    """Ensure database connection is alive, reconnect if needed"""
    try:
        connection.ensure_connection()
    except OperationalError:
        connection.close()
        connection.ensure_connection()


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ensure_connection()
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def register(self, request):
        ensure_connection()

        print(f"[v0] Register endpoint - received data: {request.data}")

        # Create a mutable copy of the data to modify username if needed
        data = request.data.copy()

        # Auto-generate unique username if collision occurs
        username = data.get('username')
        if username:
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            data['username'] = username

        serializer = RegisterSerializer(data=data)
        if serializer.is_valid():
            print(f"[v0] Serializer valid, creating user...")
            try:
                user = serializer.save()
                refresh = RefreshToken.for_user(user)
                return Response({
                    'user': UserSerializer(user).data,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }, status=status.HTTP_201_CREATED)
            except OperationalError as e:
                # Retry once on connection error
                connection.close()
                ensure_connection()
                try:
                    user = serializer.save()
                    refresh = RefreshToken.for_user(user)
                    return Response({
                        'user': UserSerializer(user).data,
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }, status=status.HTTP_201_CREATED)
                except Exception as retry_error:
                    return Response({
                        'error': f'Database connection error: {str(retry_error)}'
                    }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            except Exception as e:
                print(f"[v0] Exception during user creation: {str(e)}")
                return Response({
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        print(f"[v0] Serializer errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def login(self, request):
        ensure_connection()

        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data.get('email', '').strip()
            student_id = serializer.validated_data.get('student_id', '').strip()
            password = serializer.validated_data['password']

            try:
                user = None

                # Try to authenticate by email (admin/teacher)
                if email:
                    try:
                        user = User.objects.get(email=email)
                        if not user.check_password(password):
                            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
                    except User.DoesNotExist:
                        pass

                # Try to authenticate by student_id (students)
                if not user and student_id:
                    try:
                        student_profile = StudentProfile.objects.get(student_id=student_id)
                        user = student_profile.user
                        if not user.check_password(password):
                            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
                    except StudentProfile.DoesNotExist:
                        pass

                if user:
                    refresh = RefreshToken.for_user(user)
                    user_data = UserSerializer(user).data

                    # Add student_id if user is a student
                    if user.role == 'student':
                        try:
                            student_profile = StudentProfile.objects.get(user=user)
                            user_data['student_id'] = student_profile.student_id
                        except StudentProfile.DoesNotExist:
                            pass

                    return Response({
                        'user': user_data,
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    })

                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            except OperationalError:
                connection.close()
                return Response({
                    'error': 'Database connection error. Please try again.'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ensure_connection()
        if self.request.user.role == 'super_admin':
            return User.objects.all()
        return User.objects.filter(school=self.request.user.school)


class TeacherViewSet(viewsets.ModelViewSet):
    queryset = TeacherProfile.objects.all()
    serializer_class = TeacherProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ensure_connection()
        if self.request.user.role == 'super_admin':
            return TeacherProfile.objects.all()
        return TeacherProfile.objects.filter(user__school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        ensure_connection()
        try:
            # Get the user ID from the request (should be passed from frontend after user creation)
            user_id = request.data.get('user')
            if not user_id:
                return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            teacher_data = {
                'user': user_id,
                'employee_id': request.data.get('employee_id'),
                'qualification': request.data.get('qualification', ''),
                'experience_years': request.data.get('experience_years', 0),
                'department': request.data.get('department'),
                'bio': request.data.get('bio', ''),
            }

            serializer = self.get_serializer(data=teacher_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except OperationalError:
            connection.close()
            return Response({
                'error': 'Database connection error. Please try again.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StudentViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ensure_connection()
        class_id = self.request.query_params.get('class_id')

        queryset = StudentProfile.objects.all()

        if self.request.user.role == 'super_admin':
            return queryset

        queryset = queryset.filter(user__school=self.request.user.school)

        if class_id:
            student_ids = StudentClass.objects.filter(class_obj_id=class_id).values_list('student__id', flat=True)
            queryset = queryset.filter(user_id__in=student_ids)

        return queryset

    def create(self, request, *args, **kwargs):
        ensure_connection()
        try:
            print(f"[v0] StudentProfile create - received data: {request.data}")

            # Get the user ID from the request (should be passed from frontend after user creation)
            user_id = request.data.get('user')
            if not user_id:
                return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            student_data = {
                'user': user_id,
                'level': request.data.get('level'),
                'department': request.data.get('department'),
                # student_id is auto-generated in the model's save() method
            }

            serializer = self.get_serializer(data=student_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        except IntegrityError as e:
            # This might still happen if there's a unique constraint violation on another field
            print(f"[v0] StudentProfile create integrity error: {str(e)}")
            return Response({'error': f'A database integrity error occurred: {e}'}, status=status.HTTP_400_BAD_REQUEST)
        except OperationalError:
            connection.close()
            return Response({
                'error': 'Database connection error. Please try again.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            print(f"[v0] StudentProfile create error: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminStaffViewSet(viewsets.ModelViewSet):
    """ViewSet for managing admin staff accounts and permissions"""
    permission_classes = [IsAuthenticated, IsSchoolAdminOrHigher]
    queryset = User.objects.all() # queryset is required for ModelViewSet

    def get_serializer_class(self):
        """
        Use AdminStaffCreateSerializer for creating staff (to handle password),
        and UserSerializer for all other actions.
        """
        if self.action == 'create':
            return AdminStaffCreateSerializer
        return UserSerializer

    def get_queryset(self):
        """Only show admin staff for the same school"""
        admin_roles = ['academic_admin', 'exam_officer', 'finance_officer', 'ct_admin_support']
        
        if self.request.user.role == 'super_admin':
            return User.objects.filter(role__in=admin_roles)
        
        # A non-super_admin should have a school context
        if not self.request.user.school:
             return User.objects.none()

        return User.objects.filter(
            role__in=admin_roles,
            school=self.request.user.school
        )

    def perform_create(self, serializer):
        """Override perform_create to handle school assignment and RolePermission."""
        # For a school admin, automatically assign their school to the new user
        if self.request.user.role == 'school_admin':
            school = self.request.user.school
            user = serializer.save(school=school)
        else:
            # For super_admin, the school should be in the request data
            user = serializer.save()

        # Handle RolePermission creation
        permissions = self.request.data.get('permissions', [])
        RolePermission.objects.create(user=user, permission=permissions)

    @action(detail=True, methods=['put', 'patch'])
    def permissions(self, request, pk=None):
        """Update permissions for an admin staff member"""
        user = self.get_object()
        permissions = request.data.get('permissions', [])
        
        role_perm, created = RolePermission.objects.get_or_create(user=user)
        role_perm.permission = permissions
        role_perm.save()
        
        return Response({'status': 'success', 'message': 'Permissions updated successfully.'})
