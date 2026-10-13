import os
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_health_reports_database_connection(self):
        response = self.client.get(reverse('health'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'database': 'ok'})

    def test_version_reports_configured_release_identity(self):
        with patch.dict(os.environ, {'APEX_VERSION': '2026.10.04-001', 'GIT_COMMIT': 'abc1234'}):
            response = self.client.get(reverse('version'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'version': '2026.10.04-001', 'commit': 'abc1234'})
        self.assertNotIn('secret', response.content.decode().lower())

    @patch('apex_backend.urls.connection.ensure_connection', side_effect=OperationalError)
    def test_health_returns_unavailable_when_database_is_offline(self, ensure_connection):
        response = self.client.get(reverse('health'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable', 'database': 'unavailable'})
