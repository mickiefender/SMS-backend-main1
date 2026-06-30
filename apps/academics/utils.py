from django.template import Template, Context
from django.utils.safestring import mark_safe
from django.db.models import Avg, Sum, Count, Q
from django.db import transaction
from django.contrib.auth import get_user_model
import bleach
from datetime import timedelta
from .models import (
    TerminalReportTemplate, TerminalReport, SubjectScore, Subject, Class, 
    AcademicSession, StudentClass, ClassSubjectTeacher, GradingScale
)
from apps.schools.models import School
from apps.users.models import User
from apps.attendance.models import Attendance
from apps.students.models import Grade
from apps.academics.models import ClassSubject  # For class subjects

User = get_user_model()

SAFE_TAGS = [
    'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b', 'em', 'i', 'u',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'ul', 'ol', 'li', 'br', 'hr', 'img', 'a'
]

SAFE_ATTRS = ['href', 'src', 'alt', 'width', 'height', 'style', 'class', 'id', 'align']

def sanitize_html(html_content):
    """Sanitize HTML to prevent XSS"""
    return bleach.clean(
        html_content,
        tags=SAFE_TAGS,
        attributes=SAFE_ATTRS,
        styles=['color', 'background-color', 'font-size', 'font-family', 'text-align', 'margin', 'padding', 'width', 'height'],
        strip=True
    )

def render_template_html(template_id, student_data):
    """Render template HTML with student data"""
    try:
        template_obj = TerminalReportTemplate.objects.get(id=template_id)
        html_template = template_obj.html_template or ''
        
        # Replace variables
        context = get_render_context(student_data)
        
        # Django template render for safety
        t = Template(html_template)
        rendered = t.render(Context(context))
        
        return sanitize_html(rendered)
    except TerminalReportTemplate.DoesNotExist:
        return "<p>Template not found</p>"
    except Exception as e:
        return f"<p>Error rendering template: {str(e)}</p>"

def get_render_context(student_data):
    """Get context dict for template rendering"""
    context = {
        'student_name': student_data.get('student_name', 'N/A'),
        'class_name': student_data.get('class_name', 'N/A'),
        'school_name': student_data.get('school_name', 'N/A'),
        'total_score': student_data.get('total_score', 0),
        'position': student_data.get('position', 'N/A'),
        'attendance': f"{student_data.get('attendance_percentage', 0)}%",
        'teacher_remark': student_data.get('teacher_remark', ''),
        # subjects_table generated below
    }
    
    # Generate subjects table HTML
    subjects_table = generate_subjects_table(student_data.get('subject_scores', []))
    context['subjects_table'] = mark_safe(subjects_table)
    
    return context

def generate_subjects_table(subject_scores):
    """Generate HTML table for subjects"""
    if not subject_scores:
        return '<p>No subjects found</p>'
    
    html = '''
    <table style="width:100%; border-collapse: collapse; border: 1px solid #ddd;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Subject</th>
                <th style="padding: 12px; text-align: center; border: 1px solid #ddd;">Score</th>
                <th style="padding: 12px; text-align: center; border: 1px solid #ddd;">Grade</th>
                <th style="padding: 12px; text-align: center; border: 1px solid #ddd;">Position</th>
            </tr>
        </thead>
        <tbody>
    '''
    
    for score in subject_scores:
        html += f'''
            <tr>
                <td style="padding: 12px; border: 1px solid #ddd;">{score.get("subject_name", "N/A")}</td>
                <td style="padding: 12px; text-align: center; border: 1px solid #ddd; font-weight: bold;">{score.get("percentage", 0)}%</td>
                <td style="padding: 12px; text-align: center; border: 1px solid #ddd;">
                    <span style="background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">
                        {score.get("grade", "N/A")}
                    </span>
                </td>
                <td style="padding: 12px; text-align: center; border: 1px solid #ddd;">{score.get("subject_position", "N/A")}/{score.get("subject_total_students", "N/A")}</td>
            </tr>
        '''
    
    html += '''
        </tbody>
    </table>
    '''
    return html

def get_grade_letter(percentage):
    """Get grade letter from percentage"""
    if percentage >= 90:
        return 'A'
    elif percentage >= 80:
        return 'B'
    elif percentage >= 70:
        return 'C'
    elif percentage >= 60:
        return 'D'
    else:
        return 'F'

def calculate_student_report_data(student_id, class_id, session_id):
    """
    Calculate complete student report data for terminal report generation.
    Returns dict with:
      - success: bool
      - aggregates: TerminalReport field values
      - subject_scores: list of per-subject computed values
    """
    try:
        student = User.objects.get(id=student_id, role='student')
        cls = Class.objects.get(id=class_id)
        session = AcademicSession.objects.get(id=session_id)

        # Verify student in class
        if not StudentClass.objects.filter(
            student=student, class_obj=cls, is_active=True
        ).exists():
            return {'success': False, 'error': 'Student not enrolled in this class'}

        # Active class students (single source for ranking scope)
        class_student_ids = list(
            StudentClass.objects.filter(class_obj=cls, is_active=True)
            .values_list('student_id', flat=True)
        )
        total_students = len(class_student_ids)

        # Attendance for session period
        session_attendance = Attendance.objects.filter(
            student=student,
            class_obj=cls,
            date__gte=session.start_date,
            date__lte=session.end_date
        )
        days_present = session_attendance.filter(status='present').count()
        total_days = session_attendance.values('date').distinct().count()
        attendance_percentage = (days_present / total_days * 100) if total_days > 0 else 0

        # Get class subjects with names in one query
        class_subjects = ClassSubject.objects.filter(class_obj=cls).select_related('subject')

        subject_scores = []
        subject_totals_for_average = []

        for class_subject in class_subjects:
            subject = class_subject.subject

            # Final subject score = sum of effective percentages from locked grades
            # (Grade.percentage already stores weighted contribution when policy applies)
            student_subject_total = Grade.objects.filter(
                student_id=student_id,
                subject=subject,
                academic_session=session,
                is_locked=True
            ).aggregate(total=Sum('percentage'))['total'] or 0.0

            # Ranking basis for this subject (one row per student in class)
            subject_student_totals = list(
                Grade.objects.filter(
                    student_id__in=class_student_ids,
                    subject=subject,
                    academic_session=session,
                    is_locked=True
                )
                .values('student_id')
                .annotate(total=Sum('percentage'))
                .order_by('-total', 'student_id')
            )

            subject_total_students = len(subject_student_totals)
            subject_position = None
            for idx, row in enumerate(subject_student_totals, start=1):
                if row['student_id'] == student_id:
                    subject_position = idx
                    break

            grade = get_grade_letter(student_subject_total)

            subject_scores.append({
                'subject_id': subject.id,
                'subject_name': subject.name,
                'total_score': float(student_subject_total),
                'percentage': float(student_subject_total),
                'grade': grade,
                'remarks': '',
                'subject_position': subject_position,
                'subject_total_students': subject_total_students
            })

            subject_totals_for_average.append(float(student_subject_total))

        average_marks = (
            sum(subject_totals_for_average) / len(subject_totals_for_average)
            if subject_totals_for_average else 0.0
        )
        total_marks = average_marks
        overall_grade = get_grade_letter(average_marks)

        # Overall ranking: for each class student, average across subject totals
        student_overall_rows = []
        for sid in class_student_ids:
            sid_subject_totals = list(
                Grade.objects.filter(
                    student_id=sid,
                    subject_id__in=[cs.subject_id for cs in class_subjects],
                    academic_session=session,
                    is_locked=True
                )
                .values('subject_id')
                .annotate(total=Sum('percentage'))
            )

            sid_avg = (
                sum(float(r['total'] or 0.0) for r in sid_subject_totals) / len(sid_subject_totals)
                if sid_subject_totals else 0.0
            )
            student_overall_rows.append({'student_id': sid, 'avg': sid_avg})

        student_overall_rows.sort(key=lambda x: (-x['avg'], x['student_id']))

        position = None
        for idx, row in enumerate(student_overall_rows, start=1):
            if row['student_id'] == student_id:
                position = idx
                break

        # Determine promotion status based on grading scale
        promotion_status = 'unknown'
        try:
            # Get default grading scale for this school/session
            grading_scale = GradingScale.objects.filter(
                school=cls.school,
                academic_session=session,
                is_active=True,
                is_default=True
            ).prefetch_related('entries').first()
            
            if grading_scale and grading_scale.entries.exists():
                # Find the grade entry matching the overall percentage
                for entry in grading_scale.entries.all():
                    if entry.min_percentage <= average_marks <= entry.max_percentage:
                        if entry.promotion_eligible:
                            promotion_status = 'promoted'
                        else:
                            promotion_status = 'repeated'
                        break
            else:
                # Fallback: simple pass/fail
                promotion_status = 'promoted' if average_marks >= 60 else 'repeated'
        except Exception:
            promotion_status = 'unknown'

        # Determine best subject
        best_subject_name = ''
        best_subject_score = 0
        if subject_scores:
            best = max(subject_scores, key=lambda x: x['percentage'])
            best_subject_name = best['subject_name']
            best_subject_score = best['percentage']

        aggregates = {
            'total_marks': round(float(total_marks), 2),
            'average_marks': round(float(average_marks), 2),
            'position': position,
            'total_students': total_students,
            'grade': overall_grade,
            'total_days': total_days,
            'days_present': days_present,
            'attendance_percentage': round(float(attendance_percentage), 2),
            'promotion_status': promotion_status,
            'best_subject_name': best_subject_name,
            'best_subject_score': round(float(best_subject_score), 2),
            'form_teacher_remarks': '',
            'principal_remarks': ''
        }

        return {
            'success': True,
            'aggregates': aggregates,
            'subject_scores': subject_scores
        }

    except User.DoesNotExist:
        return {'success': False, 'error': 'Student not found'}
    except (Class.DoesNotExist, AcademicSession.DoesNotExist):
        return {'success': False, 'error': 'Class or session not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
