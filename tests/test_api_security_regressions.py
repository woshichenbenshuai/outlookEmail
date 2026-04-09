import importlib
import os
import tempfile
import unittest


os.environ.setdefault('SECRET_KEY', '0123456789abcdef0123456789abcdef')
os.environ.setdefault('DISABLE_SCHEDULER', '1')
_temp_dir = tempfile.mkdtemp(prefix='outlookEmail-api-tests-')
os.environ['DATABASE_PATH'] = os.path.join(_temp_dir, 'test.db')

web_outlook_app = importlib.import_module('web_outlook_app')


class ApiSecurityRegressionTests(unittest.TestCase):
    def setUp(self):
        self.client = web_outlook_app.app.test_client()
        web_outlook_app.app.config['WTF_CSRF_ENABLED'] = False
        web_outlook_app.app.config['WTF_CSRF_CHECK_DEFAULT'] = False
        with web_outlook_app.app.app_context():
            db = web_outlook_app.get_db()
            db.execute('DELETE FROM accounts')
            db.execute("DELETE FROM settings WHERE key IN ('external_api_key', 'login_password')")
            db.commit()

    def _login(self):
        with self.client.session_transaction() as session:
            session['logged_in'] = True
            session.permanent = True

    def test_internal_emails_requires_login(self):
        response = self.client.get('/api/emails/user@example.com')
        self.assertEqual(response.status_code, 401)
        payload = response.get_json()
        self.assertFalse(payload['success'])
        self.assertTrue(payload.get('need_login'))

    def test_external_emails_requires_api_key(self):
        response = self.client.get('/api/external/emails?email=user@example.com')
        self.assertEqual(response.status_code, 401)
        payload = response.get_json()
        self.assertFalse(payload['success'])
        self.assertIn('API Key', payload.get('error', ''))

    def test_internal_emails_rejects_non_integer_top(self):
        with web_outlook_app.app.app_context():
            created = web_outlook_app.add_account(
                'user@example.com', 'password123', 'client-id', 'refresh-token', 1
            )
            self.assertTrue(created)

        self._login()
        response = self.client.get('/api/emails/user@example.com?top=abc')
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload['success'])
        self.assertIn('top', payload.get('error', ''))

    def test_external_emails_rejects_non_integer_top(self):
        with web_outlook_app.app.app_context():
            saved = web_outlook_app.set_setting('external_api_key', 'test-key')
            self.assertTrue(saved)

        response = self.client.get(
            '/api/external/emails?email=user@example.com&top=abc',
            headers={'X-API-Key': 'test-key'},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload['success'])
        self.assertIn('top', payload.get('error', ''))

    def test_settings_hides_login_password_hash(self):
        with web_outlook_app.app.app_context():
            hashed = web_outlook_app.hash_password('super-strong-password')
            saved = web_outlook_app.set_setting('login_password', hashed)
            self.assertTrue(saved)

        self._login()
        response = self.client.get('/api/settings')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        settings = payload.get('settings', {})
        self.assertNotIn('login_password', settings)
        self.assertEqual(settings.get('login_password_masked'), '******')

    def test_update_account_status_rejects_invalid_value(self):
        with web_outlook_app.app.app_context():
            created = web_outlook_app.add_account(
                'status@example.com', 'password123', 'client-id', 'refresh-token', 1
            )
            self.assertTrue(created)
            account = web_outlook_app.get_account_by_email('status@example.com')
            self.assertIsNotNone(account)
            account_id = account['id']

        self._login()
        response = self.client.put(f'/api/accounts/{account_id}', json={'status': 'paused'})
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload['success'])
        self.assertIn('active / inactive', payload.get('error', ''))


if __name__ == '__main__':
    unittest.main()
