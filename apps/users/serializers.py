from rest_framework import serializers
from django.contrib.auth import authenticate
from apps.users.models import User, TeacherProfile, StudentProfile
import random


def generate_unique_username(school, first_name, last_name):
    """
    Generate unique username for students
    Format: [FIRST_LETTER_OF_FIRST_NAME][LAST_NAME][RANDOM_NUMBER]
    Example: dAsante123, mJohn456
    """
    base_username = f"{first_name[0].lower()}{last_name.lower()}".replace(" ", "")[:15]
    
    # Check if username already exists and generate a unique one
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        # Add a number suffix to make it unique
        random_num = random.randint(1000, 9999)
        username = f"{base_username}{random_num}"[:30]  # Keep it under 30 chars (Django User model limit)
        counter += 1
        if counter > 100:  # Safety check to prevent infinite loop
            username = f"{base_username}{random.randint(100000, 999999)}"[:30]
            break
    
    return username



class UserSerializer(serializers.ModelSerializer):
    school_id = serializers.IntegerField(source='school.id', read_only=True, allow_null=True)
    school_name = serializers.CharField(source='school.name', read_only=True, allow_null=True)
    school_logo = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'username', 'phone', 'role', 'school', 'school_id', 'school_name', 'school_logo', 'is_active_user', 'created_at', 'permissions', 'profile_picture']
        read_only_fields = ['id', 'created_at', 'school_id']
    
    def get_permissions(self, obj):
        try:
            return obj.role_permission.permission if hasattr(obj, 'role_permission') and obj.role_permission else []
        except:
            return []

    def get_profile_picture(self, obj):
        try:
            profile_pic = getattr(obj, 'profile_picture', None)
            if profile_pic:
                return profile_pic.display_url
        except Exception:
            pass
        return None

    def get_school_logo(self, obj):
        """Get the school logo URL from the related school"""
        try:
            if obj.school:
                return obj.school.get_logo_url()
        except Exception:
            pass
        return None


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ['email', 'username', 'first_name', 'last_name', 'password', 'password2', 'phone', 'role', 'school']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        
        # For students, generate a unique username
        if attrs.get('role') == 'student':
            school = attrs.get('school')
            first_name = attrs.get('first_name', '')
            last_name = attrs.get('last_name', '')
            
            attrs['username'] = generate_unique_username(school, first_name, last_name)
        
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    """Support both email (for admin/teacher) and student_id (for students) login"""
    email = serializers.EmailField(required=False, allow_blank=True)
    student_id = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email', '').strip()
        student_id = attrs.get('student_id', '').strip()
        
        if not email and not student_id:
            raise serializers.ValidationError("Either email or student_id must be provided.")
        
        return attrs


class AdminStaffCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('email', 'username', 'first_name', 'last_name', 'password', 'phone', 'role', 'school')

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class TeacherProfileSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    user_data = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = [
            'id', 'user', 'user_data', 'user_email', 'user_name',
            'first_name', 'last_name', 'email', 'username', 'phone',
            'employee_id', 'qualification', 'experience_years', 'department', 'bio',
            'gender', 'date_of_birth', 'address', 'specialization',
            'profile_picture_url',
            'created_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'employee_id',
            'user_email', 'user_name', 'first_name', 'last_name',
            'email', 'username', 'phone', 'user_data',
        ]

    def get_user_data(self, obj):
        if obj.user:
            return {
                'id': obj.user.id,
                'email': obj.user.email,
                'first_name': obj.user.first_name,
                'last_name': obj.user.last_name,
                'username': obj.user.username,
                'phone': obj.user.phone,
                'role': obj.user.role,
            }
        return None

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return None
    
    def get_profile_picture_url(self, obj):
        """Get profile picture URL from UserProfilePicture or TeacherProfile"""
        # First try the profile_picture relation
        try:
            if hasattr(obj, 'user') and obj.user:
                profile_pic = getattr(obj.user, 'profile_picture', None)
                if profile_pic:
                    return profile_pic.display_url
        except Exception:
            pass
        # Fallback to profile_picture_url field on teacher profile
        return getattr(obj, 'profile_picture_url', None)


class StudentProfileSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_data = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    profile_picture_url = serializers.SerializerMethodField()
    school_logo = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            'id', 'user', 'user_id', 'user_data', 'user_email', 'user_name',
            'first_name', 'last_name', 'email', 'username', 'phone',
            'student_id', 'level', 'department', 'enrollment_date',
            'gender', 'father_name', 'mother_name', 'religion',
            'father_occupation', 'address', 'roll_number', 'date_of_birth',
            'profile_picture_url', 'school_logo',
            'created_at',
        ]
        read_only_fields = [
            'id', 'enrollment_date', 'created_at', 'student_id', 'user_id',
            'user_email', 'user_name', 'first_name', 'last_name',
            'email', 'username', 'phone', 'user_data',
        ]

    def get_user_data(self, obj):
        if obj.user:
            return {
                'id': obj.user.id,
                'email': obj.user.email,
                'first_name': obj.user.first_name,
                'last_name': obj.user.last_name,
                'username': obj.user.username,
                'phone': obj.user.phone,
                'role': obj.user.role,
            }
        return None

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return None
    
    def get_profile_picture_url(self, obj):
        """Get profile picture URL from UserProfilePicture or StudentProfile"""
        # First try the profile_picture relation
        try:
            if hasattr(obj, 'user') and obj.user:
                profile_pic = getattr(obj.user, 'profile_picture', None)
                if profile_pic:
                    return profile_pic.display_url
        except Exception:
            pass
        # Fallback to profile_picture_url field on student profile
        return getattr(obj, 'profile_picture_url', None)

    def get_school_logo(self, obj):
        """Get the student's school logo URL (fallback avatar for students
        without a profile picture)."""
        try:
            if obj.user and obj.user.school:
                return obj.user.school.get_logo_url()
        except Exception:
            pass
        return None
