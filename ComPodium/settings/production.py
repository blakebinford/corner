import os

from django.conf.global_settings import CSRF_TRUSTED_ORIGINS

from .base import *
from decouple import config
import dj_database_url

SECRET_KEY = os.environ.get("SECRET_KEY")
DEBUG = False

ALLOWED_HOSTS = ['atlascompetition.com', 'www.atlascompetition.com']
SECURE_SSL_REDIRECT = True
CSRF_TRUSTED_ORIGINS = ['https://atlascompetition.com']

# Production Database
DATABASES = {
    'default': dj_database_url.config(conn_max_age=600)
}

# Security settings
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True

# Static Files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = "atlascompetition"
AWS_S3_REGION_NAME = "us-east-2"
AWS_S3_CUSTOM_DOMAIN = f"media.atlascompetition.com"

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

MEDIA_URL = f"{AWS_S3_CUSTOM_DOMAIN}/"
AWS_QUERYSTRING_AUTH = False
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_PORT = config('SENDGRID_SMTP_PORT')
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'apikey' # This is always "apikey" for SendGrid
EMAIL_HOST_PASSWORD = config('SENDGRID_API_KEY')  # Your actual API key
DEFAULT_FROM_EMAIL = 'noreply@atlascompetition.com'  # Use your domain
