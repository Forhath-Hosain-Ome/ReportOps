import os
from pathlib import Path
from datetime import timedelta
import sys
from celery.schedules import crontab
from dotenv import load_dotenv

import logging


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(os.path.join(BASE_DIR, '.env'))

FIELD_ENCRYPTION_KEY = os.environ.get('FIELD_ENCRYPTION_KEY', '')

# Allow importing the top-level workspace `analysis` package from backend code.
WORKSPACE_ROOT = BASE_DIR.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

WORKSPACE_ROOT = BASE_DIR.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

SECRET_KEY = os.environ.get('SECRET_KEY', '')


DEBUG = True

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'backend',
]

INSTALLED_APPS = [
    'daphne',
    'channels',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'corsheaders',

    'puma_summary.apps.PumaSummaryConfig',
    'image_processor.apps.ImageProcessorConfig',
    'final_summary.apps.FinalSummaryConfig',
    'top_five.apps.TopFiveConfig',
    'mail_download.apps.MailDownloadConfig',
    'inspection_summary.apps.InspectionSummaryConfig',
    'encrypted_model_fields',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

ROOT_URLCONF = 'summary_backend.urls'

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",  
        "rest_framework.authentication.BasicAuthentication",    
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
 
    # Pagination — BatchListView uses 20, ReportListView uses 50
    # (each view overrides page_size via paginate_by / pagination_class)
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
 
    # Consistent error format for React
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
 
    # Date/time formatting
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",
    "DATE_FORMAT":     "%Y-%m-%d",
}

# ── Simple JWT ────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
 
    "ROTATE_REFRESH_TOKENS":    True,   
    "BLACKLIST_AFTER_ROTATION": True,
 
    "ALGORITHM":              "HS256",
    "AUTH_HEADER_TYPES":      ("Bearer",),
    "AUTH_HEADER_NAME":       "HTTP_AUTHORIZATION",
    "USER_ID_FIELD":          "id",
    "USER_ID_CLAIM":          "user_id",
 
    "TOKEN_OBTAIN_SERIALIZER":  "rest_framework_simplejwt.serializers.TokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSerializer",
}

# ── Django Channels ───────────────────────────────────────────────────────────
WSGI_APPLICATION = 'summary_backend.wsgi.application'
ASGI_APPLICATION = 'summary_backend.asgi.application'   # adjust to your project name
 
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(os.getenv('REDIS_HOST', 'REDIS_HOST_DEV'), int(os.getenv('REDIS_PORT', 'REDIS_PORT_DEV')))],
            # Optional tuning
            "capacity":  1500,   # max messages queued per channel
            "expiry":    60,     # seconds before unread messages are dropped
        },
    }
}

# ── CORS (React dev server) ────────────────────────────────────────────────────
# Allow the React dev server to call the API without CORS errors.
# In production, replace with your actual frontend domain.
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:5173",   # Vite default
#     "http://localhost:3000",   # CRA default
# ]

# extra_host = os.getenv('DJANGO_ALLOWED_HOST')
# if extra_host:
#     CORS_ALLOWED_ORIGINS.append(extra_host)
ALLOWED_HOSTS = ['*']

CORS_ALLOW_ALL_ORIGINS = True

# Allow credentials (cookies, authorization headers) for cross-origin requests
CORS_ALLOW_CREDENTIALS = True

# Allow the Authorization header so Bearer tokens work cross-origin
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'summary_backend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'POSTGRES_DB_DEV'),
        'USER': os.getenv('POSTGRES_USER', 'POSTGRES_USER_DEV'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'POSTGRES_PASSWORD_DEV'),
        'HOST': os.getenv('POSTGRES_HOST', 'POSTGRES_HOST_DEV'),
        'PORT': os.getenv('POSTGRES_PORT', 'POSTGRES_PORT_DEV'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Templates files

TEMPLATE_URL = "/media/templates/"
TEMPLATE_ROOT = MEDIA_ROOT / "templates"

# Log files
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class AppUserDateHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self._cache = set()

    """Routes logs to logs/<app>/<username>/<date>.log"""
    def emit(self, record):
        try:
            from datetime import date
            app      = getattr(record, 'app', record.name.split('.')[0])
            username = getattr(record, 'username', 'system')
            day      = date.today().strftime('%Y-%m-%d')

            log_path = LOG_DIR / app / username
            log_path.mkdir(parents=True, exist_ok=True)

            file_path = log_path / f"{day}.log"
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(self.format(record) + '\n')
        except Exception:
            # Fallback to stderr if file logging fails (e.g., permission issues)
            import sys
            print(self.format(record), file=sys.stderr)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{asctime} [{levelname}] {name}: {message}',
            'style': '{',
        },
        'extraction': {
            'format': '{asctime} [{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_app': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'app.log'),
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'extraction',
        },
        'file_final_summary': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'final_summary' / 'extraction.log'),
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'extraction',
        },
    },
    'root': {
        'handlers': ['console', 'file_app'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_app'],
            'level': 'INFO',
            'propagate': False,
        },
        'final_summary': {
            'handlers': ['console', 'file_final_summary', 'file_app'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'final_summary.tasks': {
            'handlers': ['console', 'file_final_summary', 'file_app'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'final_summary.extraction': {
            'handlers': ['console', 'file_final_summary', 'file_app'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file_app'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

PUMA_SETTINGS = {
    "CERTIFICATE_TEMPLATE_PATH": TEMPLATE_ROOT / "CERTIFICATE.docx",
    "OUTPUT_DIR":        MEDIA_ROOT / "output/puma",
    "RENAMED_PDF_DIR":   MEDIA_ROOT / "output/puma/renamed_pdfs",
    "CERTIFICATE_DIR":   MEDIA_ROOT / "output/puma/certificates",
}

IMAGE_PROCESSOR_SETTINGS = {
    "DEFECT_IMAGE_TEMPLATE_PATH": TEMPLATE_ROOT / "Defec_pictures.docx",
    "OUTPUT_DIR" :        MEDIA_ROOT / "output/defect_image",
    "DEFECT_PDF" :        MEDIA_ROOT / "output/defect_image/renamed_pdfs",
    "DEFECT_DOCX":        MEDIA_ROOT / "output/defect_image/defect_docx",
}

TOP_FIVE_SETTINGS = {
    "TOP_FIVE_TEMPLATE_PATH": TEMPLATE_ROOT / "template.xlsx",
    "OUTPUT_DIR" :        MEDIA_ROOT / "output/top_five",
}

# Celery Setup


CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'CELERY_BROKER_URL_DEV')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

CELERY_TASK_DEFAULT_QUEUE = 'celery'
CELERY_TASK_ROUTES = {
    'puma_summary.process_inspection_batch': {'queue': 'puma_summary'},
    'puma_summary.retry_failed_pdfs':        {'queue': 'puma_summary'},
    'image_processor.process_defect_docx':   {'queue': 'image_processor'},
    'final_summary.process_audit_upload':    {'queue': 'celery'},
    'top_five.run_top5_job':                 {'queue': 'celery'},
}

CELERY_BEAT_SCHEDULE = {
    "inspection-summary-cleanup-hourly": {
        "task": "inspection_summary.cleanup_expired",
        "schedule": crontab(minute=15),
    },
    # Runs every day at 02:00 AM server time
    "cleanup-temp-dirs-daily": {
        "task":     "image_processor.cleanup_temp_dirs",
        "schedule": crontab(hour=2, minute=0),
    },
}