from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from django.db import connection, OperationalError, IntegrityError, transaction
from django.db.models import Count, Q
from core.permissions import IsSchoolAdminOrHigher, IsSuperAdmin, CanManageAdminStaff
from apps.users.models import User, TeacherProfile, StudentProfile, RolePermission, ParentStudentRelationship
from apps.academics.models import StudentClass
from apps.users.serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer, AdminStaffCreateSerializer,
    TeacherProfileSerializer, StudentProfileSerializer, ParentSerializer, ParentStudentRelationshipSerializer
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

    def get_permissions(self):
        if self.action in ['ban_user', 'suspend_user', 'reset_password', 'assign_global_role', 'global_stats']:
            return [IsAuthenticated(), IsSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        ensure_connection()
        queryset = User.objects.all()

        if self.request.user.role != 'super_admin':
            queryset = queryset.filter(school=self.request.user.school)

        school_id = self.request.query_params.get('school_id')
        role = self.request.query_params.get('role')
        is_active_user = self.request.query_params.get('is_active_user')

        if school_id:
            queryset = queryset.filter(school_id=school_id)
        if role:
            queryset = queryset.filter(role=role)
        if is_active_user in ['true', 'false']:
            queryset = queryset.filter(is_active_user=(is_active_user == 'true'))

        return queryset

    @action(detail=True, methods=['post'])
    def ban_user(self, request, pk=None):
        user = self.get_object()
        user.is_active_user = False
        user.is_active = False
        user.save(update_fields=['is_active_user', 'is_active', 'updated_at'])
        return Response({'status': 'success', 'message': 'User banned successfully'})

    @action(detail=True, methods=['post'])
    def suspend_user(self, request, pk=None):
        user = self.get_object()
        user.is_active_user = False
        user.save(update_fields=['is_active_user', 'updated_at'])
        return Response({'status': 'success', 'message': 'User suspended successfully'})

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        user = self.get_object()
        new_password = request.data.get('new_password')
        if not new_password:
            return Response({'error': 'new_password is required'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'status': 'success', 'message': 'Password reset successfully'})

    @action(detail=True, methods=['post'])
    def assign_global_role(self, request, pk=None):
        user = self.get_object()
        new_role = request.data.get('role')
        allowed_global_roles = ['ct_admin_support', 'academic_admin', 'exam_officer', 'finance_officer', 'super_admin']

        if not new_role:
            return Response({'error': 'role is required'}, status=status.HTTP_400_BAD_REQUEST)
        if new_role not in allowed_global_roles:
            return Response({'error': f'Invalid role. Allowed: {allowed_global_roles}'}, status=status.HTTP_400_BAD_REQUEST)

        user.role = new_role
        user.save(update_fields=['role', 'updated_at'])
        return Response({'status': 'success', 'message': 'Global role assigned successfully', 'role': user.role})

    @action(detail=False, methods=['get'])
    def global_stats(self, request):
        by_role = User.objects.values('role').annotate(count=Count('id')).order_by('role')
        return Response({
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active_user=True).count(),
            'inactive_users': User.objects.filter(is_active_user=False).count(),
            'users_by_role': by_role,
        })


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
            user_id = request.data.get('user')
            if not user_id:
                return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.get(id=user_id)
            print(f"[v0] Creating TeacherProfile for user {user_id}, school_id={getattr(user, 'school_id', None)}")

            teacher_data = {
                'user': user_id,
                # employee_id auto-generated in model.save()
                'qualification': request.data.get('qualification', ''),
                'experience_years': request.data.get('experience_years', 0),
                'department': request.data.get('department'),
                'bio': request.data.get('bio', ''),
            }

            serializer = self.get_serializer(data=teacher_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            print(f"[v0] TeacherProfile created successfully: {serializer.data['id']}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except User.DoesNotExist:
            return Response({'error': f'User ID {user_id} not found'}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as e:
            print(f"[v0] IntegrityError creating TeacherProfile: {str(e)}")
            return Response({'error': f'Database integrity error (likely duplicate/missing required field): {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except OperationalError:
            connection.close()
            return Response({
                'error': 'Database connection error. Please try again.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[v0] Unexpected error creating TeacherProfile: {str(e)}")
            return Response({'error': f'Unexpected error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        """
        Update both the linked User record (name, email, phone, username)
        and the TeacherProfile record (employee_id, qualification, etc.).
        The frontend never sends the 'user' PK, so we cannot rely on the
        default serializer validation — we update the ORM objects directly.
        """
        ensure_connection()
        instance = self.get_object()

        try:
            # ── 1. Update User fields ──────────────────────────────────────
            user = instance.user
            user_dirty = False
            for field in ('first_name', 'last_name', 'email', 'username', 'phone'):
                value = request.data.get(field)
                if value not in (None, ''):
                    setattr(user, field, value)
                    user_dirty = True
            if request.data.get('password'):
                user.set_password(request.data['password'])
                user_dirty = True
            if user_dirty:
                user.save()

            # ── 2. Update TeacherProfile fields ───────────────────────────
            # employee_id not editable - auto-generated
            if 'qualification' in request.data:
                instance.qualification = request.data['qualification']
            if 'bio' in request.data:
                instance.bio = request.data['bio']

            # Accept both 'experience_years' (serializer name) and
            # 'experience' (frontend field name)
            exp_raw = request.data.get('experience_years') or request.data.get('experience')
            if exp_raw is not None:
                try:
                    instance.experience_years = int(exp_raw)
                except (ValueError, TypeError):
                    pass

            if 'department' in request.data:
                instance.department_id = request.data['department'] or None

            # ── 3. Extended personal fields ────────────────────────────────
            if 'gender' in request.data:
                instance.gender = request.data['gender'] or None
            if 'date_of_birth' in request.data and request.data['date_of_birth']:
                instance.date_of_birth = request.data['date_of_birth']
            elif 'date_of_birth' in request.data and not request.data['date_of_birth']:
                instance.date_of_birth = None
            if 'address' in request.data:
                instance.address = request.data['address'] or ''
            if 'specialization' in request.data:
                instance.specialization = request.data['specialization'] or ''

            instance.save()

            serializer = self.get_serializer(instance)
            return Response(serializer.data)

        except OperationalError:
            connection.close()
            return Response(
                {'error': 'Database connection error. Please try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
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

    def update(self, request, *args, **kwargs):
        """
        Update both the linked User record (name, email, phone, username)
        and the StudentProfile record (level, department, date_of_birth, address, etc.).
        The frontend never sends the 'user' PK, so we update ORM objects directly.
        """
        ensure_connection()
        instance = self.get_object()

        try:
            # ── 1. Update User fields ──────────────────────────────────────
            user = instance.user
            user_dirty = False
            for field in ('first_name', 'last_name', 'email', 'username', 'phone'):
                value = request.data.get(field)
                if value not in (None, ''):
                    setattr(user, field, value)
                    user_dirty = True
            if request.data.get('password'):
                user.set_password(request.data['password'])
                user_dirty = True
            if user_dirty:
                user.save()

            # ── 2. Update StudentProfile fields ───────────────────────────
            if 'level' in request.data:
                instance.level_id = request.data['level'] or None
            if 'department' in request.data:
                instance.department_id = request.data['department'] or None
            if 'date_of_birth' in request.data and request.data['date_of_birth']:
                instance.date_of_birth = request.data['date_of_birth']
            elif 'date_of_birth' in request.data and not request.data['date_of_birth']:
                instance.date_of_birth = None

            # ── 3. Extended personal fields ────────────────────────────────
            if 'gender' in request.data:
                instance.gender = request.data['gender'] or None
            if 'father_name' in request.data:
                instance.father_name = request.data['father_name'] or ''
            if 'mother_name' in request.data:
                instance.mother_name = request.data['mother_name'] or ''
            if 'religion' in request.data:
                instance.religion = request.data['religion'] or ''
            if 'father_occupation' in request.data:
                instance.father_occupation = request.data['father_occupation'] or ''
            if 'address' in request.data:
                instance.address = request.data['address'] or ''
            if 'roll_number' in request.data:
                instance.roll_number = request.data['roll_number'] or ''

            instance.save()

            serializer = self.get_serializer(instance)
            return Response(serializer.data)

        except OperationalError:
            connection.close()
            return Response(
                {'error': 'Database connection error. Please try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        ensure_connection()
        try:
            print(f"[users] Student profile create - received data: {request.data}")

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


class ParentViewSet(viewsets.ModelViewSet):
    serializer_class = ParentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = User.objects.filter(role='parent').select_related('school').prefetch_related(
            'parent_student_relationships__student__student_profile',
            'parent_student_relationships__student__school',
        )
        if self.request.user.role == 'parent':
            return queryset.filter(pk=self.request.user.pk)
        if self.request.user.role == 'super_admin':
            school_id = self.request.query_params.get('school_id')
            return queryset.filter(school_id=school_id) if school_id else queryset
        return queryset.filter(school_id=self.request.user.school_id)

    def create(self, request, *args, **kwargs):
        print(f"[users] Parent account create - received student_ids: {request.data.get('student_ids', [])}")
        if request.user.role not in ('school_admin', 'super_admin'):
            return Response({'detail': 'Only a school administrator can create parent accounts.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'school_admin' and not request.user.school_id:
            return Response({'detail': 'The administrator is not assigned to a school.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        student_ids = data.get('student_ids', [])
        if not isinstance(student_ids, list):
            return Response({'student_ids': 'Provide a list of student user IDs.'}, status=status.HTTP_400_BAD_REQUEST)
        school_id = request.user.school_id if request.user.role == 'school_admin' else data.get('school')
        if not school_id:
            return Response({'school': 'A school is required.'}, status=status.HTTP_400_BAD_REQUEST)
        requested_student_ids = {str(student_id).strip() for student_id in student_ids if str(student_id).strip()}
        numeric_student_ids = {int(student_id) for student_id in requested_student_ids if student_id.isdigit()}
        if not requested_student_ids:
            return Response({'student_ids': 'Select at least one student.'}, status=status.HTTP_400_BAD_REQUEST)

        students = list(User.objects.filter(
            id__in=numeric_student_ids,
            role='student',
            school_id=school_id,
        ))
        profiles = StudentProfile.objects.filter(
            Q(id__in=numeric_student_ids) | Q(student_id__in=requested_student_ids),
            user__role='student',
            user__school_id=school_id,
        ).select_related('user')
        students.extend(profile.user for profile in profiles)
        students = list({student.id: student for student in students}.values())
        matched_ids = {str(student.id) for student in students}
        matched_ids.update(
            identifier
            for profile in profiles
            for identifier in (str(profile.id), profile.student_id)
            if identifier
        )

        if not students or not requested_student_ids.issubset(matched_ids):
            return Response({
                'detail': 'The selected student was not found in the administrator’s school.',
                'received_ids': sorted(requested_student_ids),
                'matched_ids': sorted(matched_ids),
            }, status=status.HTTP_400_BAD_REQUEST)
        required = ('email', 'first_name', 'last_name', 'password')
        missing = {field: 'This field is required.' for field in required if not data.get(field)}
        if missing:
            return Response(missing, status=status.HTTP_400_BAD_REQUEST)

        base_username = f"{data['first_name'][0]}{data['last_name']}".lower().replace(' ', '')[:25] or 'parent'
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}{suffix}'
            suffix += 1

        try:
            with transaction.atomic():
                parent = User.objects.create_user(
                    username=username,
                    email=data['email'].strip().lower(),
                    first_name=data['first_name'].strip(),
                    last_name=data['last_name'].strip(),
                    password=data['password'],
                    phone=data.get('phone', ''),
                    role='parent',
                    school_id=school_id,
                )
                ParentStudentRelationship.objects.bulk_create([
                    ParentStudentRelationship(
                        parent=parent,
                        student=student,
                        relationship_type=data.get('relationship_type', 'guardian'),
                        status='approved',
                        created_by=request.user,
                    )
                    for student in students
                ])
        except IntegrityError as error:
            return Response({
                'detail': 'The parent account could not be created because it conflicts with existing data.',
                'error': str(error),
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(ParentSerializer(parent).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='link')
    def link_existing(self, request):
        if request.user.role not in ('school_admin', 'super_admin'):
            return Response({'detail': 'Only a school administrator can link students.'}, status=status.HTTP_403_FORBIDDEN)

        parent_id = request.data.get('parent_id')
        student_ids = request.data.get('student_ids', [])
        if not parent_id or not isinstance(student_ids, list) or not student_ids:
            return Response({'detail': 'parent_id and at least one student_id are required.'}, status=status.HTTP_400_BAD_REQUEST)

        parent = self.get_queryset().filter(id=parent_id).first()
        if not parent or (request.user.role == 'school_admin' and parent.school_id != request.user.school_id):
            return Response({'detail': 'Parent account not found in your school.'}, status=status.HTTP_404_NOT_FOUND)
        school_id = parent.school_id

        try:
            numeric_ids = {int(value) for value in student_ids}
        except (TypeError, ValueError):
            return Response({'detail': 'Student IDs must be numeric user IDs.'}, status=status.HTTP_400_BAD_REQUEST)

        students = list(User.objects.filter(
            id__in=numeric_ids, role='student', school_id=school_id,
        ))
        if len(students) != len(numeric_ids):
            return Response({'detail': 'One or more students were not found in your school.'}, status=status.HTTP_400_BAD_REQUEST)

        relationship_type = request.data.get('relationship_type', 'guardian')
        if relationship_type not in dict(ParentStudentRelationship.RELATIONSHIP_CHOICES):
            return Response({'relationship_type': 'Use mother, father, guardian, or other.'}, status=status.HTTP_400_BAD_REQUEST)

        relationships = []
        for student in students:
            relationship, _ = ParentStudentRelationship.objects.update_or_create(
                parent=parent,
                student=student,
                defaults={
                    'relationship_type': relationship_type,
                    'status': 'approved',
                    'created_by': request.user,
                },
            )
            relationships.append(relationship)
        return Response(ParentStudentRelationshipSerializer(relationships, many=True).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        if request.user.role != 'parent':
            return Response({'detail': 'Only parent accounts can access this dashboard.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(ParentSerializer(self.get_queryset().get(pk=request.user.pk)).data)

    @action(detail=False, methods=['get'], url_path='relationships')
    def relationships(self, request):
        queryset = ParentStudentRelationship.objects.filter(
            parent__school_id=request.user.school_id
        ).select_related('parent', 'student__student_profile', 'student__school')
        if request.user.role == 'parent':
            queryset = queryset.filter(parent=request.user)
        elif request.user.role not in ('school_admin', 'super_admin'):
            return Response({'detail': 'You do not have permission to view relationships.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(ParentStudentRelationshipSerializer(queryset, many=True).data)

    @action(detail=True, methods=['post'], url_path='relationships/(?P<relationship_id>[^/.]+)/status')
    def relationship_status(self, request, pk=None, relationship_id=None):
        if request.user.role not in ('school_admin', 'super_admin'):
            return Response({'detail': 'Only a school administrator can change relationship status.'}, status=status.HTTP_403_FORBIDDEN)
        relationship = ParentStudentRelationship.objects.filter(
            id=relationship_id, parent_id=pk, parent__school_id=request.user.school_id,
        ).first()
        if not relationship:
            return Response({'detail': 'Relationship not found.'}, status=status.HTTP_404_NOT_FOUND)
        new_status = request.data.get('status')
        if new_status not in dict(ParentStudentRelationship.STATUS_CHOICES):
            return Response({'status': 'Use pending, approved, or revoked.'}, status=status.HTTP_400_BAD_REQUEST)
        relationship.status = new_status
        relationship.save(update_fields=['status', 'updated_at'])
        return Response(ParentStudentRelationshipSerializer(relationship).data)

    @action(detail=False, methods=['delete'], url_path='relationships/(?P<relationship_id>[^/.]+)/remove')
    def remove_relationship(self, request, relationship_id=None):
        if request.user.role not in ('school_admin', 'super_admin'):
            return Response({'detail': 'Only a school administrator can remove relationships.'}, status=status.HTTP_403_FORBIDDEN)
        relationship_query = ParentStudentRelationship.objects.filter(id=relationship_id)
        if request.user.role == 'school_admin':
            relationship_query = relationship_query.filter(parent__school_id=request.user.school_id)
        relationship = relationship_query.first()
        if not relationship:
            return Response({'detail': 'Relationship not found.'}, status=status.HTTP_404_NOT_FOUND)
        relationship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def my_classes(self, request):
        """
        Get classes assigned to the teacher.
        This endpoint returns classes where the teacher is either a ClassTeacher (form tutor)
        or a ClassSubjectTeacher (subject teacher).
        """
        ensure_connection()
        
        try:
            from apps.academics.models import Class, ClassTeacher, ClassSubjectTeacher
            
            # Get class IDs where teacher is a ClassTeacher (form tutor)
            class_teacher_class_ids = ClassTeacher.objects.filter(
                teacher=request.user
            ).values_list('class_obj_id', flat=True)
            
            # Get class IDs where teacher is a ClassSubjectTeacher (subject teacher)
            subject_teacher_class_ids = ClassSubjectTeacher.objects.filter(
                teacher=request.user
            ).values_list('class_obj_id', flat=True)
            
            # Combine all class IDs
            all_class_ids = set(list(class_teacher_class_ids) + list(subject_teacher_class_ids))
            
            print(f"[TeacherClasses] Teacher: {request.user.id}, Classes: {all_class_ids}")
            
            if not all_class_ids:
                return Response({
                    'count': 0,
                    'results': [],
                    'message': 'No classes assigned to this teacher'
                })
            
            # Get class details
            classes = Class.objects.filter(id__in=all_class_ids).select_related('level')
            
            results = []
            for cls in classes:
                # Get student count for this class
                student_count = StudentClass.objects.filter(
                    class_obj=cls,
                    is_active=True
                ).count()
                
                # Check if teacher is form tutor
                is_form_tutor = ClassTeacher.objects.filter(
                    teacher=request.user,
                    class_obj=cls
                ).exists()
                
                # Get subjects taught by this teacher in this class
                subjects_taught = ClassSubjectTeacher.objects.filter(
                    teacher=request.user,
                    class_obj=cls
                ).select_related('subject').values(
                    'subject__id', 'subject__name', 'subject__code'
                )
                
                results.append({
                    'id': cls.id,
                    'name': cls.name,
                    'class_code': cls.code,  # Changed from 'code' to 'class_code' for frontend compatibility
                    'level': cls.level.name if cls.level else None,
                    'student_count': student_count,
                    'is_form_tutor': is_form_tutor,
                    'subjects_taught': [
                        {
                            'id': s['subject__id'],
                            'name': s['subject__name'],
                            'code': s['subject__code']
                        }
                        for s in subjects_taught
                    ]
                })
            
            print(f"[TeacherClasses] Found {len(results)} classes")
            
            return Response({
                'count': len(results),
                'results': results
            })
            
        except Exception as e:
            import traceback
            print(f"[TeacherClasses] Error: {str(e)}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def my_students(self, request):
        """
        Get students enrolled in the teacher's classes.
        This endpoint returns students assigned to classes where the teacher
        is either a ClassTeacher (form tutor) or a ClassSubjectTeacher (subject teacher).
        """
        ensure_connection()
        
        try:
            # Get school_id from user
            school_id = getattr(request.user, 'school_id', None)
            if not school_id and hasattr(request.user, 'school'):
                school_id = getattr(request.user.school, 'id', None)
            
            # Get all classes where this teacher is assigned (as form tutor or subject teacher)
            from apps.academics.models import ClassTeacher, ClassSubjectTeacher, UserProfilePicture
            
            # Get class IDs where teacher is a ClassTeacher (form tutor)
            class_teacher_class_ids = ClassTeacher.objects.filter(
                teacher=request.user
            ).values_list('class_obj_id', flat=True)
            
            # Get class IDs where teacher is a ClassSubjectTeacher (subject teacher)
            subject_teacher_class_ids = ClassSubjectTeacher.objects.filter(
                teacher=request.user
            ).values_list('class_obj_id', flat=True)
            
            # Combine all class IDs
            all_class_ids = set(list(class_teacher_class_ids) + list(subject_teacher_class_ids))
            
            print(f"[TeacherStudents] Teacher: {request.user.id}, Classes: {all_class_ids}")
            
            if not all_class_ids:
                return Response({
                    'count': 0,
                    'results': [],
                    'message': 'No classes assigned to this teacher'
                })
            
            # Get students enrolled in these classes - student is already a FK to User
            student_class_entries = StudentClass.objects.filter(
                class_obj_id__in=all_class_ids,
                is_active=True
            ).select_related('student', 'class_obj')
            
            # Build unique student list with their class info
            students_dict = {}
            for entry in student_class_entries:
                student_user = entry.student  # This is the User object directly
                if student_user and student_user.id not in students_dict:
                    # Get StudentProfile for additional fields
                    try:
                        student_profile = StudentProfile.objects.get(user=student_user)
                        student_id = student_profile.student_id
                        gender = student_profile.gender
                        level = student_profile.level.name if student_profile.level else None
                        roll_number = student_profile.roll_number
                    except StudentProfile.DoesNotExist:
                        student_id = None
                        gender = None
                        level = None
                        roll_number = None
                    
                    # Get profile picture URL
                    profile_picture_url = None
                    try:
                        profile_pic = UserProfilePicture.objects.get(user=student_user)
                        profile_picture_url = profile_pic.storage_url or (profile_pic.picture.url if profile_pic.picture else None)
                    except UserProfilePicture.DoesNotExist:
                        profile_picture_url = None
                    
                    students_dict[student_user.id] = {
                        'id': student_user.id,
                        'user': {
                            'id': student_user.id,
                            'first_name': student_user.first_name,
                            'last_name': student_user.last_name,
                            'email': student_user.email,
                        },
                        'student_id': student_id,
                        'gender': gender,
                        'level': level,
                        'class': {
                            'id': entry.class_obj.id,
                            'name': entry.class_obj.name,
                        },
                        'roll_number': roll_number,
                        'profile_picture': profile_picture_url,
                    }
            
            results = list(students_dict.values())
            
            print(f"[TeacherStudents] Found {len(results)} unique students")
            
            return Response({
                'count': len(results),
                'results': results
            })
            
        except Exception as e:
            import traceback
            print(f"[TeacherStudents] Error: {str(e)}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=500)


class AdminStaffViewSet(viewsets.ModelViewSet):
    """ViewSet for managing admin staff accounts and permissions"""
    # School admins always manage staff; admin-staff with 'manage_admins' may too.
    permission_classes = [IsAuthenticated, CanManageAdminStaff]
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
