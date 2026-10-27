from .base import *
import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

DEBUG = False


def required_setting(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise ImproperlyConfigured(f'{name} must be configured in production.')
    return value


def required_origins(name):
    origins = [
        origin.strip()
        for origin in required_setting(name).split(',')
        if origin.strip()
    ]
    parsed_origins = [urlparse(origin) for origin in origins]
    if not origins or any(
        parsed.scheme != 'https'
        or not parsed.netloc
        or parsed.path not in ('', '/')
        or parsed.query
        or parsed.fragment
        or '*' in origin
        for origin, parsed in zip(origins, parsed_origins)
    ):
        raise ImproperlyConfigured(f'{name} must contain HTTPS origins only.')
    return origins


required_setting('DATABASE_URL')
if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured('Production requires DATABASE_URL configured for PostgreSQL.')

SECRET_KEY = required_setting('DJANGO_SECRET_KEY')
if SECRET_KEY == 'dev-insecure-fallback-key-do-not-use-in-production':
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must not use the development fallback.')

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', '').split(',')
    if host.strip()
]
render_external_hostname = os.environ.get(
    'RENDER_EXTERNAL_HOSTNAME', ''
).strip()
if render_external_hostname:
    ALLOWED_HOSTS.insert(0, render_external_hostname)

if not ALLOWED_HOSTS or any('*' in host or '://' in host or '/' in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        'Set ALLOWED_HOSTS or deploy on Render with '
        'RENDER_EXTERNAL_HOSTNAME configured. Use explicit production hostnames.'
    )

CORS_ALLOWED_ORIGINS = required_origins('CORS_ALLOWED_ORIGINS')
CSRF_TRUSTED_ORIGINS = required_origins('CSRF_TRUSTED_ORIGINS')

EMAIL_HOST = required_setting('EMAIL_HOST')
EMAIL_HOST_USER = required_setting('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = required_setting('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = required_setting('DEFAULT_FROM_EMAIL')

FRONTEND_URL = required_setting('FRONTEND_URL')
if urlparse(FRONTEND_URL).scheme != 'https' or not urlparse(FRONTEND_URL).netloc:
    raise ImproperlyConfigured('FRONTEND_URL must be an HTTPS URL in production.')

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
