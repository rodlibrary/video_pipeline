"""A tiny OpenAI-compatible HTTP server for tests (chat completions + embeddings).

It stands in for OpenAI, Ollama or LM Studio so the AI steps can be tested
offline via each config section's ``base_url``.
"""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    calls = []  # (path, body) for assertions

    def log_message(self, *_args):  # keep test output quiet
        pass

    def _send(self, payload):
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        _Handler.calls.append((self.path, body))

        if self.path.endswith("/chat/completions"):
            user = body["messages"][-1]["content"]
            has_image = isinstance(user, list) and any(p.get("type") == "image_url" for p in user)
            if body.get("response_format", {}).get("type") == "json_object":
                text = json.dumps({
                    "entities": [{"type": "organization", "label": "Test Archive"}],
                    "topics": ["testing"],
                    "keywords": ["pipeline", "fixture"],
                })
            elif has_image:
                prompt = next(p["text"] for p in user if p.get("type") == "text")
                stamp = next((ln for ln in prompt.splitlines() if ln.startswith("Timestamp")), "")
                text = f"Color bars test pattern with a moving counter. {stamp}"
            else:
                text = (
                    "A short synthetic recording produced for automated testing of the local "
                    "audiovisual pipeline. It contains a color bar test pattern and a steady tone, "
                    "with no spoken content, people, places or organizations of archival interest."
                )
            self._send({
                "id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": body.get("model"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
        elif self.path.endswith("/embeddings"):
            inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
            data = []
            for i, text in enumerate(inputs):
                digest = hashlib.sha256(text.encode()).digest()
                data.append({"object": "embedding", "index": i,
                             "embedding": [b / 255.0 for b in digest[:16]]})
            self._send({"object": "list", "data": data, "model": body.get("model"),
                        "usage": {"prompt_tokens": 1, "total_tokens": 1}})
        else:
            self.send_response(404)
            self.end_headers()


def start_server():
    """Start on a free localhost port; returns (server, base_url, calls list)."""
    _Handler.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1", _Handler.calls
