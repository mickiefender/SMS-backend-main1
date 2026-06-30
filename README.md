# School Management SaaS - Django Backend

A comprehensive multi-tenant school management system built with Django and PostgreSQL (Supabase).

## Features

- **Multi-Tenant Architecture**: Isolated school instances
- **Role-Based Access Control**: Super Admin, School Admin, Teacher, Student, Parent
- **Academic Management**: Classes, Subjects, Departments, Faculties, Levels
- **Attendance Tracking**: Daily, per-class, per-course attendance marking
- **Assessment System**: Exams, tests, quizzes, continuous assessment
- **Assignment Management**: Creation and student submissions
- **GPA Calculation**: Automatic CGPA and current GPA calculation
- **Billing System**: Invoices, payments, subscription management
- **Timetable Management**: Automated schedule creation

## Installation

### Prerequisites
- Python 3.9+
- PostgreSQL (via Supabase)
- pip

### Setup

1. **Clone the repository and navigate to backend:**
```bash
cd backend
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your Supabase credentials
```

5. **Run migrations:**
```bash
python manage.py migrate
```

6. **Create superuser:**
```bash
python manage.py createsuperuser --role=super_admin
```

7. **Run development server:**
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Authentication
- `POST /api/users/auth/register/` - Register new user
- `POST /api/users/auth/login/` - User login

### Schools (Super Admin)
- `GET/POST /api/schools/schools/` - List/Create schools
- `POST /api/schools/schools/{id}/suspend/` - Suspend school
- `POST /api/schools/schools/{id}/activate/` - Activate school

### Academics (School Admin)
- `GET/POST /api/academics/faculties/` - Manage faculties
- `GET/POST /api/academics/departments/` - Manage departments
- `GET/POST /api/academics/subjects/` - Manage subjects
- `GET/POST /api/academics/classes/` - Manage classes
- `GET/POST /api/academics/enrollments/` - Manage enrollments
- `GET/POST /api/academics/timetables/` - Create timetables

### Attendance (Teacher)
- `POST /api/attendance/bulk_mark/` - Bulk mark attendance
- `GET /api/attendance/student_report/` - Get attendance report

### Assignments (Teacher/Student)
- `GET/POST /api/assignments/` - Create assignments
- `POST /api/assignments/submissions/submit/` - Submit assignment
- `POST /api/assignments/submissions/{id}/grade/` - Grade submission

### Student Portal
- `GET /api/students/portal/my_portal/` - Get student portal data
- `GET /api/students/portal/attendance_report/` - Attendance report
- `GET /api/students/portal/exam_results/` - Exam results
- `GET /api/students/portal/assignments/` - View assignments

## Multi-Tenant Setup

Schools are isolated using the `school` foreign key. The middleware automatically extracts school context from:
1. `X-School-ID` header
2. `school_id` query parameter
3. User's school (if authenticated)

## Deployment

For production:

1. Set `DEBUG=False` in environment variables
2. Use a production WSGI server (Gunicorn)
3. Configure ALLOWED_HOSTS with your domain
4. Set secure JWT signing key
5. Use environment variables for all secrets

```bash
gunicorn core.wsgi:application
```

## Documentation

Full API documentation available at `/api/docs/` when in development mode.

## Support

For issues or questions, please contact support@schoolmanagementsaas.com
