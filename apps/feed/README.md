# Alara Learning Feed - Backend

This Django app powers the **Alara Learning Feed**, an educational short-form
content discovery platform (TikTok/YouTube Shorts style) for students,
teachers, and parents.

## Table of contents

1. [Architecture overview](#architecture-overview)
2. [Installation & setup](#installation--setup)
3. [Supabase SQL](#supabase-sql)
4. [API endpoints](#api-endpoints)
5. [Permissions](#permissions)
6. [Recommendation engine](#recommendation-engine)
7. [Background tasks](#background-tasks)
8. [Redis caching](#redis-caching)
9. [Running tests](#running-tests)

---

## Architecture overview

The backend is organized into:

```
apps/feed/
├── models.py              # All feed-related models
├── serializers.py         # DRF serializers
├── views.py               # Thin DRF viewsets / API views
├── urls.py                # URL routing
├── permissions.py         # Guest / auth / role permissions
├── pagination.py          # Cursor pagination classes
├── signals.py             # Django signals
├── tasks.py               # Celery background tasks
├── services/              # Business logic
│   ├── recommendation_service.py
│   ├── feed_service.py
│   ├── upload_service.py
│   ├── lesson_service.py
│   ├── analytics_service.py
│   ├── notification_service.py
│   ├── search_service.py
│   └── moderation_service.py
├── tests/
│   └── test_feed.py
└── sql/
    └── supabase_feed_schema.sql
```

Business logic lives in `services/`, not in views.

---

## Installation & setup

1. Install dependencies:

```bash
pip install -r backend/requirements.txt
```

2. Ensure the existing `users.User` model has a `supabase_uid` UUID column. The
   Supabase SQL script adds it safely via `ADD COLUMN IF NOT EXISTS`.

3. Run the Supabase SQL script in the Supabase SQL Editor:

```sql
-- Open backend/apps/feed/sql/supabase_feed_schema.sql and run it.
```

4. Make and run Django migrations:

```bash
cd backend
python manage.py makemigrations feed
python manage.py migrate
```

5. Add `apps.feed` to `INSTALLED_APPS` (already done in `core/settings.py`).

6. Start Celery worker:

```bash
celery -A core worker -l info
```

7. (Optional) Start Celery beat for periodic tasks:

```bash
celery -A core beat -l info
```

---

## Supabase SQL

The file `sql/supabase_feed_schema.sql` creates:

- Reference tables: academic levels, classes, subjects, tags
- Student learning profiles
- Lessons, lesson resources, tags mapping
- Likes, saves, watch history, teacher followers
- Comments, comment likes
- Notifications, reports
- Search queries, recommendation cache
- Analytics tables
- Full-text search triggers and indexes
- Materialized views for trending & popular teachers
- Supabase Storage buckets and RLS policies
- Seed data

Run it after the core Django migrations have created `users_user`,
`schools_school`, etc.

---

## API endpoints

### Feed discovery

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/feed/` | Generic feed (`?strategy=trending\|latest\|recommended`) |
| GET | `/api/feed/recommended/` | Personalized recommendations (auth) |
| GET | `/api/feed/trending/` | Trending feed |
| GET | `/api/feed/latest/` | Latest lessons |
| GET | `/api/feed/search/?q=algebra` | Full-text search |
| GET | `/api/feed/continue-watching/` | Continue watching (auth) |
| GET | `/api/feed/watch-history/` | Watch history (auth) |

### Lessons

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/feed/lesson/` | List lessons |
| POST | `/api/feed/lesson/` | Upload lesson (teacher) |
| GET | `/api/feed/lesson/{id}/` | Lesson detail |
| PATCH | `/api/feed/lesson/{id}/` | Update lesson (owner/admin) |
| DELETE | `/api/feed/lesson/{id}/` | Delete lesson (owner/admin) |
| POST | `/api/feed/lesson/{id}/like/` | Toggle like |
| POST | `/api/feed/lesson/{id}/save/` | Toggle save |
| POST | `/api/feed/lesson/{id}/watch/` | Record watch event |
| POST | `/api/feed/lesson/{id}/share/` | Record share |
| POST | `/api/feed/lesson/{id}/download/` | Record download |
| GET | `/api/feed/lesson/{lesson_id}/comments/` | List comments |
| POST | `/api/feed/lesson/{lesson_id}/comments/` | Post comment |
| POST | `/api/feed/lesson/{lesson_id}/comments/{id}/like/` | Like comment |

### Teachers & profiles

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/feed/teacher/{id}/` | Teacher profile + lessons |
| POST | `/api/feed/teacher/{id}/follow/` | Follow teacher |
| DELETE | `/api/feed/teacher/{id}/follow/` | Unfollow teacher |

### Learning profile

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/feed/learning-profile/` | Get learning profile |
| PUT | `/api/feed/learning-profile/` | Update learning profile |

### Notifications & reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/feed/notifications/` | List notifications |
| POST | `/api/feed/notifications/{id}/mark_read/` | Mark one read |
| POST | `/api/feed/notifications/mark_all_read/` | Mark all read |
| POST | `/api/feed/reports/` | Submit report |

### Moderation (school admin+)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/feed/moderation/lesson/{id}/approve/` | Approve lesson |
| POST | `/api/feed/moderation/lesson/{id}/suspend/` | Suspend lesson |
| POST | `/api/feed/moderation/lesson/{id}/hide/` | Hide lesson |
| POST | `/api/feed/moderation/report/{id}/resolve/` | Resolve report |
| POST | `/api/feed/moderation/teacher/{id}/suspend/` | Suspend teacher |

### Reference data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/feed/reference/levels/` | Academic levels |
| GET | `/api/feed/reference/classes/` | Academic classes |
| GET | `/api/feed/reference/subjects/` | Subjects |
| GET | `/api/feed/reference/tags/` | Tags |

All list endpoints use **cursor pagination** (`?cursor=...`) for infinite
scrolling.

---

## Permissions

- **Guests** can browse public feeds, search, view lessons, comments, teacher
  profiles, and counts. Any mutating action returns `401 Unauthorized`.
- **Authenticated students/parents** can like, save, comment, follow, report,
  and personalize learning preferences.
- **Teachers** can upload, edit, and delete their own lessons.
- **School admins / super admins** can approve, suspend, hide, and resolve
  reports.

---

## Recommendation engine

### Authenticated users

Recommendations blend:

- Preferred academic level, class, and subjects
- Watch history and completion rate
- Liked / saved lessons
- Followed teachers
- Trending score, teacher quality, content freshness
- Random exploration (~10%) for diversity

### Guests

Recommendations are based on popularity signals:

- Trending
- Most viewed
- Most liked
- Newest lessons
- Highest completion rate
- Featured teachers
- Editorial picks

---

## Background tasks

Celery tasks defined in `tasks.py`:

- `process_lesson_resource` - extract metadata, generate thumbnails
- `refresh_trending_materialized_views`
- `recalculate_trending_scores`
- `aggregate_watch_metrics`
- `aggregate_daily_analytics`
- `invalidate_expired_recommendation_cache`
- `clear_stale_feed_caches`

Configure Celery beat to run the aggregation tasks periodically.

---

## Redis caching

The default Django cache backend is Redis (`django-redis`). Feed pages cache
only lesson IDs (not full serialized objects) to reduce memory and serialization
overhead. Caches are invalidated on lesson create/update/delete and via
background tasks.

---

## Running tests

```bash
cd backend
python manage.py test apps.feed.tests
```

The test suite covers models, services, permissions, recommendations,
analytics, and key API endpoints.
