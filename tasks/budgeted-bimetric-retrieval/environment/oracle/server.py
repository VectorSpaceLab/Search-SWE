"""Development-only oracle in a separate container with no external network."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import time
import numpy as np
from oracle import Oracle, QueryFailure

config = json.loads(Path('/public/config.json').read_text())
queries = [json.loads(x) for x in Path('/public/dev-queries.jsonl').read_text().splitlines()]
query_rows = {q['query_id']: i for i,q in enumerate(queries)}
query_vectors = np.memmap('/private/dev-queries.f32', dtype='<f4', mode='r', shape=(500,4096))
vectors = np.memmap('/private/expensive.f32', dtype='<f4', mode='r', shape=(config['documents'],4096))
oracle = Oracle(vectors, budget=config['score_budget'])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        self.reply(200, {'ready': True, 'budget': config['score_budget'], 'query_seconds': 2.0})

    def reply(self, code, value):
        payload = json.dumps(value, allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        try:
            self.connection.settimeout(2)
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 16384: raise ValueError('Invalid request size')
            request = json.loads(self.rfile.read(size))
            if self.path == '/begin':
                if set(request) != {'query_id'} or request['query_id'] not in query_rows:
                    raise ValueError('Only the 500 public development queries are available')
                token = secrets.token_hex(16)
                oracle.begin(query_vectors[query_rows[request['query_id']]], token, time.monotonic()+2)
                self.reply(200, {'token': token})
            elif self.path == '/score':
                self.reply(200, oracle.score(request))
            else:
                raise ValueError('Unknown endpoint')
        except (ValueError, TypeError, KeyError, QueryFailure) as exc:
            self.reply(400, {'error':str(exc)})


class UnixServer(HTTPServer):
    address_family = socket.AF_UNIX
    def server_bind(self):
        self.socket.bind(self.server_address)
        self.server_name, self.server_port = 'oracle', 0


path='/run/oracle/oracle.sock'
if os.path.exists(path): os.unlink(path)
server=UnixServer(path,Handler)
os.chmod(path,0o666)
server.serve_forever()
