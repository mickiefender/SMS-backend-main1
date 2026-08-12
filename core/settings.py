import os
from pathlib import Path
from datetime import timedelta
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment file from the backend directory (prefer .env.local, fallback to .env)
ENV_LOCAL_PATH = BASE_DIR / '.env.local'
ENV_PATH = BASE_DIR / '.env'

if ENV_LOCAL_PATH.exists():
    load_dotenv(ENV_LOCAL_PATH)
elif ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    "django.contrib.postgres",

    
    # Local apps
    'apps.users',
    'apps.schools',
    'apps.academics',
    'apps.attendance',
    'apps.assignments',
    'apps.billing',
    'apps.payments',
    'apps.students',
    'apps.storage',
    'apps.messaging',
    'apps.feed',
    'apps.notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.MultiTenantMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# Database configuration - Using Supabase PostgreSQL
DATABASES = {}

# Try to use DATABASE_URL first (Supabase standard), then fall back to individual vars
database_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')

if database_url:
    DATABASES['default'] = dj_database_url.config(
        default=database_url,
        conn_max_age=0,  # Set to 0 to create fresh connections (avoids stale connection issues)
        conn_health_checks=True,
    )
    # Ensure SSL is required for Supabase
    DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require',
        'connect_timeout': 30,  # Increased timeout
    }
else:
    # Fall back to individual environment variables
    db_name = os.environ.get('POSTGRES_DATABASE')
    if not db_name:
        raise ImproperlyConfigured(
            "Database is not configured. Set DATABASE_URL/POSTGRES_URL or POSTGRES_DATABASE in environment."
        )

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': db_name,
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '6543'),
            'CONN_MAX_AGE': 60,  # Set to 0 to avoid stale connections
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'connect_timeout': 30,
                'sslmode': 'require',
            }
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files configuration
# Use Supabase Storage if configured, otherwise fall back to local storage
USE_SUPABASE_STORAGE = os.environ.get('USE_SUPABASE_STORAGE', 'False') == 'True'

if USE_SUPABASE_STORAGE:
    # Supabase storage configuration
    STORAGES = {
        "default": {
            "BACKEND": "apps.storage.supabase_storage.SupabaseStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    MEDIA_URL = f"{os.environ.get('SUPABASE_URL')}/storage/v1/object/public/{os.environ.get('SUPABASE_STORAGE_BUCKET', 'school-documents')}/"
else:
    # Local storage configuration (default)
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# Supabase Configuration (optional - only needed if USE_SUPABASE_STORAGE=True)
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
SUPABASE_STORAGE_BUCKET = os.environ.get('SUPABASE_STORAGE_BUCKET', 'school-documents')

# Cloudflare Stream Configuration
CLOUDFLARE_STREAM_API_TOKEN = os.environ.get('CLOUDFLARE_STREAM_API_TOKEN', '')
CLOUDFLARE_STREAM_ACCOUNT_ID = os.environ.get('CLOUDFLARE_STREAM_ACCOUNT_ID', '')
CLOUDFLARE_STREAM_SIGNING_KEY = os.environ.get('CLOUDFLARE_STREAM_SIGNING_KEY', '')

# Firebase Cloud Messaging (FCM) Configuration — Firebase Admin SDK
# The Admin SDK authenticates with a service-account credential (NOT a legacy
# server key). Provide one of the two options below; PATH is preferred in
# deployments with a persistent filesystem, JSON is ideal for serverless/
# Supabase-hosted backends.
#
#  1. FIREBASE_SERVICE_ACCOUNT_PATH:
#     Path to the service-account JSON downloaded from:
#     Firebase Console → Project settings → Service accounts →
#     "Generate new private key"
#
#  2. FIREBASE_SERVICE_ACCOUNT_JSON:
#     The literal contents of that same JSON file (single line string).
FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', '')
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON', '')

# Backward-compat alias (legacy server key is no longer used by the Admin SDK)
FCM_SERVER_KEY = os.environ.get('FCM_SERVER_KEY', '')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'core.throttling.UserRoleRateThrottle',
        'core.throttling.BurstRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/minute',
        'user': '200/minute',
        'students': '50/minute',
        'teachers': '100/minute',
        'school_admins': '200/minute',
        'burst': '20/minute',
        'sustained': '1000/day',
    },
}

# JWT Configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    # Rotation + blacklisting is disabled because
    # `rest_framework_simplejwt.token_blacklist` is not installed. With
    # ROTATE_REFRESH_TOKENS=True and no blacklist app, the refresh endpoint
    # crashes trying to blacklist the old token. The mobile client keeps the
    # same refresh token for its full 7-day lifetime, which is safe.
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
CORS_ALLOW_CREDENTIALS = True

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Email Configuration (Fallback for Django mail)
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'School Management <noreply@schoolmanagement.edu>')

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.db.backends': {
            'level': 'WARNING',
            'handlers': ['console'],
        },
    },
}

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Redis Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        },
        'KEY_PREFIX': 'school_mgmt',
        'TIMEOUT': 300,  # Default timeout: 5 minutes
    }
}

# Paystack Configuration
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', 'sk_test_xxxxxxxxxxxxxxxxxxxxx')
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', 'pk_test_xxxxxxxxxxxxxxxxxxxxx')
PAYSTACK_WEBHOOK_SECRET = os.environ.get('PAYSTACK_WEBHOOK_SECRET', '')
PAYSTACK_BASE_URL = 'https://api.paystack.co'
PAYSTACK_CURRENCY = 'GHC'

# Frontend URL (for payment callbacks)
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Alara Learning Feed settings
FEED_CACHE_TIMEOUT = int(os.environ.get('FEED_CACHE_TIMEOUT', '300'))
FEED_PAGE_SIZE = int(os.environ.get('FEED_PAGE_SIZE', '12'))

# Supabase Storage buckets used by the Learning Feed
FEED_STORAGE_BUCKETS = {
    'videos': 'lesson-videos',
    'images': 'lesson-images',
    'pdfs': 'lesson-pdfs',
    'thumbnails': 'lesson-thumbnails',
    'audio': 'lesson-audio',
    'assignments': 'lesson-assignments',
    'quizzes': 'lesson-quizzes',
    'teacher_avatars': 'teacher-avatars',
}
