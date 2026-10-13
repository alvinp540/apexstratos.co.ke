from django.contrib import admin
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.analytics.views import PublicPlatformStatsView
import os


def health(request):
  try:
    connection.ensure_connection()
  except Exception:
    return JsonResponse({'status': 'unavailable', 'database': 'unavailable'}, status=503)
  return JsonResponse({'status': 'ok', 'database': 'ok'})


def version(request):
  return JsonResponse({
    'version': os.environ.get('APEX_VERSION', 'unconfigured'),
    'commit': os.environ.get('GIT_COMMIT', 'unconfigured'),
  })


def api_root(request):
    return HttpResponse(
        '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>APEX Backend</title>
    <style>
      body { align-items: center; background: #0f172a; color: #e2e8f0; display: flex; font-family: system-ui, sans-serif; justify-content: center; margin: 0; min-height: 100vh; }
      main { background: #1e293b; border: 1px solid #334155; border-radius: 16px; max-width: 520px; padding: 40px; text-align: center; }
      h1 { margin: 0 0 12px; }
      p { color: #cbd5e1; line-height: 1.6; }
      a { color: #7dd3fc; margin: 0 10px; }
      .status { color: #86efac; font-weight: 700; }
    </style>
  </head>
  <body>
    <main>
      <p class="status">● Backend running</p>
      <h1>APEX API</h1>
      <p>This service powers the APEX frontend and exposes versioned API endpoints.</p>
      <p><a href="/admin/">Django admin</a> API routes are available under <code>/api/v1/</code>.</p>
    </main>
  </body>
</html>''',
        content_type='text/html',
    )


urlpatterns = [
  path('health', health, name='health'),
  path('version', version, name='version'),
    path('', api_root, name='api-root'),
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/profiles/', include('apps.profiles.urls')),
    path('api/v1/trust/', include('apps.trust_engine.urls')),
    path('api/v1/cohorts/', include('apps.cohorts.urls')),
    path('api/v1/rankings/', include('apps.rankings.urls')),
    path('api/v1/vendor/', include('apps.vendor.urls')),
    path('api/v1/router/', include('apps.router.urls')),
    path('api/v1/escrow/', include('apps.escrow.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),
    path('api/v1/analytics/public/', PublicPlatformStatsView.as_view()),
    path('api/v1/admin/', include('apps.fraud.urls')),
    path('api/v1/social/', include('apps.social.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
