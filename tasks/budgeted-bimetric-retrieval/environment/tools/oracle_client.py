"""Public development service client. No hidden query data or model weights."""
import http.client
import json
import socket


class Connection(http.client.HTTPConnection):
    def __init__(self): super().__init__('localhost',timeout=2)
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/run/oracle/oracle.sock')


def call(path, request):
    connection=Connection()
    try:
        connection.request('POST',path,json.dumps(request),{'Content-Type':'application/json'})
        response=connection.getresponse()
        value=json.loads(response.read())
        if response.status!=200: raise RuntimeError(value.get('error','Oracle error'))
        return value
    finally:
        connection.close()
