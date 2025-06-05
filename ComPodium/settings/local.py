
from .base import *
from decouple import config
import dj_database_url

SECRET_KEY = config('SECRET_KEY', default='fallback-secret-key')
DEBUG = True


ALLOWED_HOSTS = ['*']
# settings/local.py

# during development, dump all emails to the terminal
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if DEBUG:
    INSTALLED_APPS += ['django_browser_reload']
    MIDDLEWARE += ['django_browser_reload.middleware.BrowserReloadMiddleware']


DATABASES = {
    'default': dj_database_url.config(
        "DATABASE_URL",
        default="postgres://blake:758595Aa@localhost:5432/compodium"
    )
}

AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
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

MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
AWS_QUERYSTRING_AUTH = False
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}