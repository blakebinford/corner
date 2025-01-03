from .base import *
from decouple import config
import dj_database_url

SECRET_KEY = config('SECRET_KEY', default='fallback-secret-key')
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = ['*']

if DEBUG:
    INSTALLED_APPS += ['django_browser_reload']
    MIDDLEWARE += ['django_browser_reload.middleware.BrowserReloadMiddleware']

DATABASES = {
    'default': dj_database_url.config(
        default='postgres://blake:758595Aa@localhost:5432/compodium'
    )
}

print("DATABASES: ", DATABASES)