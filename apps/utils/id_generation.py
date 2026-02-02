"""
Utility functions for generating unique codes for students, classes, and subjects
based on school initials and sequential numbers
"""

from django.db import models


def get_school_initials(school):
    """Extract initials from school name"""
    words = school.name.split()
    initials = ''.join([word[0].upper() for word in words if word])
    return initials[:3]  # Return max 3 letters


def generate_student_id(school, first_name, last_name):
    """
    Generate student ID in format: [SCHOOL_INITIALS][YEAR][SEQUENCE]
    Example: ABC2024001, ABC2024002
    """
    from datetime import datetime
    from apps.users.models import StudentProfile
    
    school_initials = get_school_initials(school)
    year = datetime.now().year
    
    # Get the count of students in this school for this year
    count = StudentProfile.objects.filter(
        user__school=school,
        created_at__year=year
    ).count() + 1
    
    student_id = f"{school_initials}{year}{count:05d}"
    return student_id


def generate_unique_username(school, first_name, last_name):
    """
    Generate unique username for students
    Format: [FIRST_LETTER_OF_FIRST_NAME][LAST_NAME][RANDOM_NUMBER]
    Example: dAsante123, mJohn456
    """
    from apps.users.models import User
    import random
    
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


def generate_class_code(school, class_name):
    """
    Generate class code in format: [SCHOOL_INITIALS]-[CLASS_SEQUENCE]
    Example: ABC-001, ABC-002
    """
    from apps.academics.models import Class
    
    school_initials = get_school_initials(school)
    
    # Get the count of classes in this school
    count = Class.objects.filter(school=school).count() + 1
    
    class_code = f"{school_initials}-{count:03d}"
    return class_code


def generate_subject_code(school, subject_name):
    """
    Generate subject code in format: [SCHOOL_INITIALS][SUBJECT_ABBR][SEQUENCE]
    Example: ABCMATH001, ABCENG002
    """
    from datetime import datetime
    from apps.academics.models import Subject
    
    school_initials = get_school_initials(school)
    
    # Get first 3 letters of subject name in uppercase
    subject_abbr = subject_name[:3].upper()
    
    # Get the count of subjects with similar names in this school
    count = Subject.objects.filter(school=school).count() + 1
    
    subject_code = f"{school_initials}{subject_abbr}{count:03d}"
    return subject_code
