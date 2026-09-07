import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vercel-api/api'))
spec = importlib.util.spec_from_file_location('personal', ROOT / 'vercel-api/api/personal_portfolio.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
UID = '11111111-1111-1111-1111-111111111111'


class PersonalApiTests(unittest.TestCase):
    def test_no_token_cannot_read_storage(self):
        with patch.object(api.requests, 'get') as get:
            status, _ = api.load_personal_portfolio('')
        self.assertEqual(status, 401)
        get.assert_not_called()

    def test_invalid_token_cannot_read_storage(self):
        with patch.object(api.sb, 'verify_jwt', return_value=None), patch.object(api.requests, 'get') as get:
            status, _ = api.load_personal_portfolio('invalid')
        self.assertEqual(status, 401)
        get.assert_not_called()

    def query(self, owner):
        response = Mock(status_code=200, content=b'{}')
        response.json.return_value = dict(schema='personal-portfolio-view-v1', owner_id=owner, rows=[])
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://example.invalid', 'SUPABASE_SERVICE_ROLE_KEY': 'test-key'}), patch.object(api.sb, 'verify_jwt', return_value=UID), patch.object(api.requests, 'get', return_value=response) as get:
            result = api.load_personal_portfolio('test-jwt')
            self.assertTrue(get.call_args.args[0].endswith('/personal/' + UID + '/latest.json'))
            self.assertTrue(get.call_args.kwargs['params']['cacheNonce'])
            return result

    def test_storage_path_uses_verified_identity(self):
        self.assertEqual(self.query(UID)[0], 200)

    def test_cross_account_payload_rejected(self):
        self.assertEqual(self.query('22222222-2222-2222-2222-222222222222')[0], 502)

    def test_storage_missing_object_is_empty_state(self):
        response = Mock(status_code=400)
        response.json.return_value = {'statusCode': '404', 'code': 'NoSuchKey'}
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://example.invalid', 'SUPABASE_SERVICE_ROLE_KEY': 'test-key'}), patch.object(api.sb, 'verify_jwt', return_value=UID), patch.object(api.requests, 'get', return_value=response):
            self.assertEqual(api.load_personal_portfolio('test-jwt')[0], 404)


if __name__ == '__main__':
    unittest.main()
