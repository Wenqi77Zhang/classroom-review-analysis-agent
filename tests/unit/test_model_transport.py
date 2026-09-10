"""Actual loopback HTTP checks for private model transport boundaries."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from agent.providers.base import ModelProviderError, ModelRequest
from agent.providers.local import LocalModelProvider


@pytest.mark.asyncio
async def test_local_model_bypasses_proxy_and_refuses_redirect(monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            requests.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/leak")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"model": "loopback-test", "choices": [{"message": {"content": '{"ok":true}'}}]}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    request = ModelRequest(system_prompt="test", user_prompt="synthetic private text", trace_id="test", response_schema={"type": "object"})
    try:
        provider = LocalModelProvider(endpoint=f"http://127.0.0.1:{server.server_port}/ok", model="test")
        assert (await provider.generate_structured(request)).data == {"ok": True}
        provider = LocalModelProvider(endpoint=f"http://127.0.0.1:{server.server_port}/redirect", model="test")
        with pytest.raises(ModelProviderError, match="重定向"):
            await provider.generate_structured(request)
        assert requests == ["/ok", "/redirect"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
