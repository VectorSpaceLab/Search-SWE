"""The audit relay exposes only the configured model, never provider credentials."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_gateway import JudgeGateway


class JudgeGatewayTests(unittest.TestCase):
    def request(self, gateway, path='/responses', model='test-model', token=None):
        req = Request(gateway.url + path,
                      data=json.dumps({'model':model, 'input':'audit data'}).encode(),
                      headers={'Authorization':'Bearer ' + (token or gateway.token),
                               'Content-Type':'application/json'})
        return urlopen(req, timeout=5)

    def test_only_parent_replaces_temporary_token_with_provider_key(self):
        with JudgeGateway('https://judge.example/v1', 'provider-secret', 'test-model') as gateway:
            upstream = MagicMock(status_code=200, headers={'Content-Type':'application/json'})
            upstream.iter_content.return_value = [b'{"ok":true}']
            upstream.__enter__.return_value = upstream
            with patch('judge_gateway.requests.post', return_value=upstream) as post:
                with self.request(gateway) as response:
                    self.assertEqual(json.load(response), {'ok':True})
                self.assertEqual(post.call_args.args[0], 'https://judge.example/v1/responses')
                self.assertEqual(post.call_args.kwargs['headers'], {'Authorization':'Bearer provider-secret'})
                self.assertNotEqual(gateway.token, 'provider-secret')

    def test_other_paths_models_and_tokens_never_reach_upstream(self):
        with JudgeGateway('https://judge.example/v1', 'provider-secret', 'test-model') as gateway:
            with patch('judge_gateway.requests.post') as post:
                for args, expected in (({'path':'/files'},404), ({'model':'other'},400), ({'token':'wrong'},403)):
                    with self.subTest(args=args), self.assertRaises(HTTPError) as raised:
                        self.request(gateway, **args)
                    self.assertEqual(raised.exception.code, expected)
                post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
