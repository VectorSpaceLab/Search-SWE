"""Retrieval API routing and credential boundaries without paid provider calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from jina_gateway import JinaGateway


class JinaTests(unittest.TestCase):
    def test_only_embeddings_and_rerank_reach_fixed_endpoints(self):
        with tempfile.TemporaryDirectory() as d:
            response = Mock(status_code=200)
            response.json.return_value = {'data': []}
            with JinaGateway('private-jina-key', float('inf'), Path(d)/'log.json') as gateway, \
                 patch('jina_gateway.requests.post', return_value=response) as post:
                with gateway.worker.makefile('rwb') as channel:
                    for op, body in (
                        ('embeddings', {'model':'jina-embeddings-v3','input':['a','b'],'task':'retrieval.passage'}),
                        ('rerank', {'model':'jina-reranker-v2-base-multilingual','query':'q','documents':['a','b'],'top_n':1}),
                    ):
                        channel.write(json.dumps({'operation':op,'body':body}).encode()+b'\n');channel.flush()
                        self.assertEqual(json.loads(channel.readline()), {'response':{'data':[]}})
                        self.assertEqual(post.call_args.args[0], 'https://api.jina.ai/v1/'+op)
                        self.assertEqual(post.call_args.kwargs['json'],body)
                        self.assertEqual(post.call_args.kwargs['headers'], {'Authorization':'Bearer private-jina-key'})
                        self.assertFalse(post.call_args.kwargs['allow_redirects'])
            self.assertNotIn('private-jina-key', (Path(d)/'log.json').read_text())

    def test_generation_url_fetch_and_endpoint_injection_are_rejected(self):
        bad = [
            {'operation':'chat/completions','body':{'model':'jina-embeddings-v3'}},
            {'operation':'../chat/completions','body':{}},
            {'operation':'embeddings','body':{'model':'','input':['a']}},
            {'operation':'embeddings','body':{'model':'jina-embeddings-v3','input':[{'url':'https://example.com'}]}},
            {'operation':'rerank','body':{'model':'jina-reranker-v2-base-multilingual','documents':['a']}},
            {'operation':'embeddings','body':{'model':'jina-embeddings-v3','input':['a']},'url':'https://example.com'},
        ]
        with tempfile.TemporaryDirectory() as d:
            with JinaGateway('key', float('inf'), Path(d)/'log.json') as gateway, patch.object(gateway,'forward') as forward:
                with gateway.worker.makefile('rwb') as channel:
                    for payload in bad:
                        channel.write(json.dumps(payload).encode()+b'\n');channel.flush()
                        self.assertIn('error',json.loads(channel.readline()))
                forward.assert_not_called()

    def test_optional_key_is_required_only_when_called(self):
        with tempfile.TemporaryDirectory() as d:
            with JinaGateway(None,float('inf'),Path(d)/'unused.json'):
                pass
            with self.assertRaises(JinaGateway.Error):
                with JinaGateway(None,float('inf'),Path(d)/'used.json') as gateway:
                    with gateway.worker.makefile('rwb') as channel:
                        channel.write(json.dumps({'operation':'embeddings','body':{'model':'jina-embeddings-v3','input':['a']}}).encode()+b'\n');channel.flush()
                        self.assertIn('error',json.loads(channel.readline()))

    def test_redirect_and_provider_error_do_not_leak_key(self):
        with tempfile.TemporaryDirectory() as d:
            gateway=JinaGateway('secret',float('inf'),Path(d)/'log.json')
            try:
                for status in (302,401,500):
                    with patch('jina_gateway.requests.post',return_value=Mock(status_code=status)):
                        with self.assertRaises(JinaGateway.Error) as error:
                            gateway.forward({'operation':'embeddings','body':{}})
                        self.assertNotIn('secret',str(error.exception))
            finally:
                gateway.parent.close();gateway.worker.close()
