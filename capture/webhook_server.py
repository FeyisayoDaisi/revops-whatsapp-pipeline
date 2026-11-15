"""
Minimal webhook receiver for the WhatsApp Cloud API (standard library only).

  GET  /webhook   Meta's verification handshake (hub.mode, hub.verify_token, hub.challenge)
  POST /webhook   checks the X-Hub-Signature-256 header, then appends the event to
                  data/webhook_events.jsonl, the same file the demo replays

Run:  WA_VERIFY_TOKEN=... WA_APP_SECRET=... python capture/webhook_server.py
Then point your Meta app's webhook (or your BSP's forwarding URL) at https://<your-host>/webhook
and subscribe to the "messages" and "smb_message_echoes" fields. In production put this behind
HTTPS and a queue; this file shows the contract, not the hosting.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

OUT = Path(__file__).resolve().parents[1] / "data" / "webhook_events.jsonl"
VERIFY = os.environ.get("WA_VERIFY_TOKEN", "")
SECRET = os.environ.get("WA_APP_SECRET", "").encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        if q.get("hub.mode") == ["subscribe"] and VERIFY and q.get("hub.verify_token") == [VERIFY]:
            self.send_response(200); self.end_headers()
            self.wfile.write(q["hub.challenge"][0].encode())
        else:
            self.send_response(403); self.end_headers()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        sig = self.headers.get("X-Hub-Signature-256", "")
        good = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        if not SECRET or not hmac.compare_digest(sig, good):
            self.send_response(401); self.end_headers(); return
        with open(OUT, "a") as f:
            f.write(json.dumps(json.loads(body), ensure_ascii=False) + "\n")
        self.send_response(200); self.end_headers()


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8080))), Handler).serve_forever()
