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

## Alara Help (Chatwoot)

The school dashboard uses the Chatwoot website widget. Configure the public
`NEXT_PUBLIC_CHATWOOT_WEBSITE_TOKEN` and optional
`NEXT_PUBLIC_CHATWOOT_BASE_URL` in the frontend deployment environment. The
widget identifies the authenticated Alara user and supplies school name, school
ID, and role as Chatwoot contact attributes.

The Super Admin Alara Help page uses Django endpoints to proxy the Chatwoot
inbox. Set `CHATWOOT_BASE_URL`, `CHATWOOT_API_TOKEN`, `CHATWOOT_ACCOUNT_ID`,
and `CHATWOOT_INBOX_ID` in the backend environment, using
[`.env.example`](./.env.example) as a reference. Do not configure private
Chatwoot API credentials in frontend environment variables. No local message
tables or migration are required: Chatwoot is the conversation store.

Configure a Chatwoot Website Inbox named **Alara Help**, use the widget token
for that inbox, and enable the inbox in the server-side `CHATWOOT_INBOX_ID`.
The Super Admin API routes are:

- `GET /api/platform/chatwoot/conversations/?status=all&page=1`
- `GET /api/platform/chatwoot/conversations/{conversation_id}/messages/`
- `POST /api/platform/chatwoot/conversations/{conversation_id}/messages/`
- `POST /api/platform/chatwoot/conversations/{conversation_id}/status/` with
  `{"status":"open"}` or `{"status":"resolved"}`

Every route requires the existing `platform.support` permission or a Super
Admin role. Messages sent from the portal are public replies to the school
conversation. The page polls Chatwoot for updates every 15 seconds.

## Caching

Django uses the configured Redis cache (`REDIS_URL`, defaulting to
`redis://localhost:6379/1`). Frequently-read response namespaces use short
TTLs: homepage content (5 minutes), school and course directories (5
minutes), teachers (2 minutes), students (1 minute), feed (1 minute), and
notifications (10 seconds). Authenticated response keys include the school,
user, role, request host, and query parameters; notification keys are also
user-scoped. Cache generations are bumped after relevant model transactions
commit, and Redis locks reduce duplicate work on cold response keys.

In development, cache `HIT`, `MISS`, `SET`, and `INVALIDATION` events are
logged. Authenticated Next.js proxy requests explicitly use `no-store`;
the browser only retains short-lived anonymous GET responses and coalesces
identical in-flight requests.

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
