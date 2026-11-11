"""Serve the learning harness and its isolated, in-memory demo sessions."""

import argparse
import json
import secrets
from collections import OrderedDict
from http.cookies import SimpleCookie
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from harness import DATA, Harness, ReviewError
from integrations.replay import cross_tool_replay

DIST = Path(__file__).with_name("web")
MAX_SESSIONS = 128


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def _session(self, *, create=False):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        cookie = cookies.get("learning_demo")
        token = cookie.value if cookie else None
        sessions = self.server.sessions
        if token in sessions:
            sessions.move_to_end(token)
            return sessions[token], None
        if not create:
            return None, None
        token = secrets.token_urlsafe(24)
        sessions[token] = Harness()
        if len(sessions) > MAX_SESSIONS:
            sessions.popitem(last=False)
        return sessions[token], token

    def _json(self, payload, status=200, token=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if token:
            self.send_header("Set-Cookie", f"learning_demo={token}; Path=/api; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/session":
            session, token = self._session(create=True)
            self._json(session.view(), token=token)
        elif self.path == "/integrations.json":
            self._json(cross_tool_replay(DATA["actions"]))
        elif self.path.split("?", 1)[0] in {"/", "/style.css", "/app.js", "/integrations.html"}:
            super().do_GET()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/session":
            self.send_error(404)
            return
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            self._json({"error": "Review actions must come from this command center."}, 403)
            return
        session, _ = self._session()
        if session is None:
            self._json({"error": "Demo session expired. Reload the page."}, 409)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 or self.headers.get_content_type() != "application/json":
                raise ValueError("Invalid review request.")
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict) or not isinstance(request.get("action"), str):
                raise ValueError("Invalid review action.")
            revision = request.get("revision")
            action_id = request.get("action_id")
            if type(revision) is not int or (action_id is not None and not isinstance(action_id, str)):
                raise ValueError("A view revision is required.")
            if request["action"] == "reset":
                if revision != session.revision:
                    raise ReviewError("Reload before resetting the case.")
                session.__init__(revision=revision + 1)
            else:
                session.apply(request["action"], revision, action_id)
        except ReviewError as exc:
            self._json({"error": str(exc)}, 409)
        except (ValueError, UnicodeError):
            self._json({"error": "Invalid review request."}, 400)
        else:
            self._json(session.view())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8796)
    args = parser.parse_args()
    with HTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.sessions = OrderedDict()
        print(f"Learning harness ready at http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
