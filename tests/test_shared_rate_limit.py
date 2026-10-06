"""No network and no member data: rate backend contract and CRUD gate tests."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rate_subject_test', ROOT / 'vercel-api/api/shared_rate_limit.py')
rate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rate)


class SharedRate(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SUPABASE_URL': 'https://example.test', 'SUPABASE_SERVICE_ROLE_KEY': 'test-only-secret'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_allowed_service_rpc_without_raw_subject(self):
        response = Mock(); response.json.return_value = {'allowed': True}
        with patch.object(rate.requests, 'post', return_value=response) as post:
            self.assertEqual(rate.consume('holdings','verified-uid'),(True,None))
        kwargs=post.call_args.kwargs
        self.assertEqual(kwargs['json']['p_scope'],'holdings')
        self.assertRegex(kwargs['json']['p_subject'],r'^[0-9a-f]{64}$')
        self.assertNotIn('verified-uid',str(kwargs))
        self.assertEqual(kwargs['timeout'],3)

    def test_denied_and_unavailable_are_distinct(self):
        response=Mock(); response.json.return_value={'allowed':False,'retry_after_sec':19}
        with patch.object(rate.requests,'post',return_value=response):
            ok,error=rate.consume('holdings','uid'); self.assertFalse(ok); self.assertEqual(error['status'],429)
        with patch.object(rate.requests,'post',side_effect=TimeoutError('private-value')):
            ok,error=rate.consume('holdings','uid'); self.assertFalse(ok); self.assertEqual(error['status'],503)
            self.assertNotIn('private-value',str(error))

    def test_missing_config_and_bad_results_fail_closed(self):
        with patch.dict(os.environ,{'SUPABASE_SERVICE_ROLE_KEY':''}), patch.object(rate.requests,'post') as post:
            self.assertEqual(rate.consume('holdings','uid')[1]['status'],503); post.assert_not_called()
        for body in [[],{'allowed':'yes'},{'allowed':False},{'allowed':False,'retry_after_sec':True},{'allowed':False,'retry_after_sec':999999}]:
            response=Mock(); response.json.return_value=body
            with patch.object(rate.requests,'post',return_value=response):
                self.assertEqual(rate.consume('holdings','uid')[1]['status'],503)

    def test_anonymous_counter_has_bounded_subjects(self):
        response=Mock(); response.json.return_value={'allowed':True}
        with patch.object(rate.requests,'post',return_value=response) as post:
            rate.consume('visitor_ping','192.0.2.1')
            digest=post.call_args.kwargs['json']['p_subject']
            self.assertEqual(digest[3:],'0'*61)

    def test_forwarded_headers_only_trusted_on_vercel(self):
        handler=Mock(headers={'x-vercel-forwarded-for':'192.0.2.1','x-forwarded-for':'192.0.2.2'},client_address=('127.0.0.1',1))
        with patch.dict(os.environ,{'VERCEL':'1'}): self.assertEqual(rate.client_ip(handler),'192.0.2.1')
        with patch.dict(os.environ,{'VERCEL':'0'}): self.assertEqual(rate.client_ip(handler),'127.0.0.1')

    def test_survey_uses_separate_bounded_ip_budget(self):
        response = Mock(); response.json.return_value = {'allowed': True}
        with patch.object(rate.requests, 'post', return_value=response) as post:
            self.assertEqual(rate.consume('survey', '192.0.2.1'), (True, None))
            subject = post.call_args.kwargs['json']['p_subject']
            self.assertEqual(post.call_args.kwargs['json']['p_scope'], 'survey')
        self.assertRegex(subject, r'^[a-f0-9]{3}0{61}$')
        self.assertNotEqual(subject, rate.subject_digest('visitor_ping', '192.0.2.1', 'test-only-secret'))

    def test_invalid_scope_does_not_call_backend(self):
        with patch.object(rate.requests, 'post') as post:
            self.assertEqual(rate.consume('untrusted', '192.0.2.1')[1]['status'], 503)
            post.assert_not_called()


if __name__=='__main__': unittest.main()
