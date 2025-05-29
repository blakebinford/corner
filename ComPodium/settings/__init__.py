import os
from decouple import config

env = config('DJANGO_ENV', default='local')

if env == 'prod':
    from .production import *
else:
    from .local import *