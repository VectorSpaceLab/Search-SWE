"""A small concurrent, read-only BM25 search service over SQLite FTS5."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

STOPWORDS = set("a an and are as at be by for from how i in is it of on or that the their this to was were what when where which who with would".split())


def search(database, query, top_k=10):
    terms = list(dict.fromkeys(t.casefold() for t in re.findall(r"[^\W_]+", query)))
    terms = [t for t in terms if t not in STOPWORDS][:24]
    expression = " OR ".join('"' + t + '"' for t in terms)
    with sqlite3.connect(f"file:{quote(str(database))}?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT docid, substr(text, 1, 1000), url FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
            (expression, top_k),
        ).fetchall() if expression else []
        # A query with no lexical matches still has valid candidate IDs.
        if len(rows) < 5:
            seen = {r[0] for r in rows}
            for row in db.execute("SELECT docid, substr(text, 1, 1000), url FROM docs LIMIT 5"):
                if row[0] not in seen:
                    rows.append(row)
    return [{"docid": row[0], "text": row[1], "url": row[2]} for row in rows[:top_k]]


def serve(database, runtime, token):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/health":
                self.send_error(404)
                return
            self.reply({"database": str(database), "token": token})

        def do_POST(self):
            if self.path != "/search":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100_000:
                    raise ValueError("invalid request length")
                body = json.loads(self.rfile.read(length))
                query = body["query"]
                if not isinstance(query, str):
                    raise ValueError("query must be a string")
                top_k = max(5, min(30, int(body.get("top_k", 10))))
                self.reply({"documents": search(database, query, top_k)})
            except (ValueError, KeyError, sqlite3.Error):
                self.send_error(400, "invalid search request")

        def reply(self, value):
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    runtime.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "token": token, "pid": os.getpid()}) + "\n")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    serve(args.database.resolve(), args.runtime, args.token)
