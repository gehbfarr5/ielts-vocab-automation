from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .ingest import MAX_BYTES, receive
from .store import Store


def serve(root: Path, token: str, host="127.0.0.1", port=8766):
    if len(token) < 32:
        raise ValueError("Use a random intake token of at least 32 characters")
    if host != "127.0.0.1":
        raise ValueError("Bind loopback; use a separately reviewed TLS/private-network proxy")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log URLs, headers, tokens, or screenshot contents.

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def respond(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

        def do_POST(self):
            if not self.authorized():
                return self.respond(401, {"error": "unauthorized"})
            if self.path != "/v1/submissions":
                return self.respond(404, {"error": "not_found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BYTES:
                    return self.respond(413, {"error": "invalid_length"})
                if self.headers.get("Content-Type", "").split(";")[0] not in (
                    "image/png",
                    "image/jpeg",
                    "image/webp",
                ):
                    return self.respond(415, {"error": "send_raw_image_body"})
                data = self.rfile.read(size)
                if len(data) != size:
                    raise ValueError("Incomplete body")
                store = Store(root / "state.sqlite3")
                try:
                    receipt = receive(store, root, data, self.headers.get("Idempotency-Key"))
                finally:
                    store.db.close()
                self.respond(202, receipt)
            except (ValueError, OSError) as e:
                self.respond(400, {"error": type(e).__name__})

        def do_GET(self):
            if not self.authorized():
                return self.respond(401, {"error": "unauthorized"})
            store = Store(root / "state.sqlite3")
            try:
                path = urlsplit(self.path).path
                if path == "/v1/status":
                    return self.respond(200, store.status())
                prefix = "/v1/submissions/"
                if path.startswith(prefix):
                    row = store.db.execute(
                        "SELECT id,state,error FROM submissions WHERE id=?", (path[len(prefix) :],)
                    ).fetchone()
                    if row:
                        return self.respond(200, dict(row))
                self.respond(404, {"error": "not_found"})
            finally:
                store.db.close()

    HTTPServer((host, port), Handler).serve_forever()


def token_from_file(path):
    p = Path(path)
    if p.stat().st_mode & 0o077:
        raise ValueError("Token file must be readable by its owner only (mode 0600)")
    if p.stat().st_uid != os.getuid():
        raise ValueError("Token file owner mismatch")
    return p.read_text().strip()
