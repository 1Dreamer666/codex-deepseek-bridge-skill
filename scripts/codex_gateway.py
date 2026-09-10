"""Loopback Responses router. Never persists request bodies or authentication headers."""
from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL = "deepseek-v4.1-flash"
LUNA_ALIAS = "gpt-5.6-luna"
LOCK = threading.Lock()


def audit(path, **event):
    with LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), **event}) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def error(self, status, message):
        data = json.dumps({"error": {"message": message}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self.error(200, "gateway_alive")
        else:
            self.error(404, "Unknown endpoint")

    def do_POST(self):
        route = self.path.removeprefix("/v1")
        if route not in ("/responses", "/responses/compact"):
            return self.error(404, "Unknown endpoint")
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32 * 1024 * 1024:
                return self.error(413, "Invalid body size")
            body = self.rfile.read(size)
            payload = json.loads(body)
            model = payload.get("model", "")
            routed_model = model
            if model in (MODEL, LUNA_ALIAS):
                import codex_staryears
                secret = codex_staryears.manager.read_credential_key()
                if not secret:
                    return self.error(503, "Staryears credential missing")
                target = "https://api.staryears.net/v1/responses"
                headers = {"Authorization": "Bearer " + secret, "Content-Type": "application/json", "Accept": "text/event-stream"}
                upstream = "staryears"
                payload["model"] = MODEL
                body = json.dumps(payload).encode()
            elif model in self.server.openai_models:
                target = self.server.openai_base + route
                excluded = {"host", "content-length", "connection", "transfer-encoding", "accept-encoding"}
                headers = {k: v for k, v in self.headers.items() if k.lower() not in excluded}
                upstream = "openai"
            else:
                return self.error(400, "Model not in configured catalog")
            headers["Accept-Encoding"] = "identity"
            request = urllib.request.Request(target, body, headers, method="POST")
            try:
                response = urllib.request.urlopen(request, timeout=180)
            except urllib.error.HTTPError as exc:
                response = exc
            audit(self.server.audit, model=model, routed_model=payload.get("model", routed_model), upstream=upstream, status=response.status, route=route,
                  input_types=sorted({x.get("type", "message") for x in payload.get("input", []) if isinstance(x, dict)}))
            raw = response.read()
            content_type = response.headers.get("Content-Type", "application/json")
            if upstream == "staryears" and "application/json" in content_type:
                result = json.loads(raw)
                raw = b"event: response.completed\ndata: " + json.dumps({"type":"response.completed","response":result}, ensure_ascii=False).encode() + b"\n\ndata: [DONE]\n\n"
                content_type = "text/event-stream"
            self.send_response(response.status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            self.wfile.write(raw)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            audit(self.server.audit, error_type=type(exc).__name__)
            if not self.close_connection:
                self.error(502, "Upstream transport error")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=18741)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--openai-base", choices=["https://chatgpt.com/backend-api/codex", "https://api.openai.com/v1"], default="https://chatgpt.com/backend-api/codex")
    args = p.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.audit = args.audit
    server.openai_base = args.openai_base
    server.openai_models = {m["slug"] for m in json.loads(args.catalog.read_text(encoding="utf-8"))["models"] if m["slug"].startswith("gpt-")}
    print(json.dumps({"status": "listening", "port": args.port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
