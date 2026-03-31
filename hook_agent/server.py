from __future__ import annotations

import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .event_store import EventStore


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "web"
LOG_DIR = ROOT_DIR / "log"
SERVER_HOST = os.environ.get("HOOK_AGENT_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("HOOK_AGENT_PORT", "8765"))
APPROVAL_TIMEOUT_SECONDS = int(os.environ.get("HOOK_AGENT_APPROVAL_TIMEOUT", "3600"))
REQUIRE_APPROVAL = os.environ.get("HOOK_AGENT_REQUIRE_APPROVAL", "1") != "0"
APPROVAL_HOOK_EVENTS = {"PreToolUse", "BeforeTool"}

STORE = EventStore(LOG_DIR)


def json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class HookAgentHandler(BaseHTTPRequestHandler):
    server_version = "hookAgent/0.1"

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._serve_static("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/sessions":
            json_response(self, {"sessions": STORE.get_sessions_summary()})
            return
        if parsed.path.startswith("/api/sessions/"):
            session_id = parsed.path.rsplit("/", 1)[-1]
            detail = STORE.get_session_detail(session_id)
            if detail is None:
                json_response(self, {"error": "Session not found"}, status=404)
                return
            json_response(self, detail)
            return
        if parsed.path == "/api/approvals":
            json_response(self, {"approvals": STORE.get_all_pending_approvals()})
            return
        if parsed.path == "/api/events/stream":
            self._serve_event_stream()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/hook-event":
            self._handle_hook_event()
            return
        if parsed.path.startswith("/api/approvals/") and parsed.path.endswith("/decision"):
            approval_id = parsed.path.split("/")[-2]
            self._handle_approval_decision(approval_id)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _serve_static(self, name: str, content_type: str) -> None:
        target = STATIC_DIR / name
        if not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _handle_hook_event(self) -> None:
        payload = self._read_json_body()
        event = STORE.add_event(payload)
        if event["hook_event_name"] not in APPROVAL_HOOK_EVENTS or not REQUIRE_APPROVAL:
            json_response(self, {"hook_response": {}})
            return

        approval = STORE.create_approval(event)
        decision = STORE.wait_for_approval(approval["approval_id"], APPROVAL_TIMEOUT_SECONDS)
        hook_response = self._build_hook_response(payload, decision)
        json_response(self, {"hook_response": hook_response, "approval_id": approval["approval_id"]})

    def _build_hook_response(self, payload: dict[str, Any], decision: dict[str, str]) -> dict[str, Any]:
        hook_event_name = payload.get("hook_event_name", "")
        agent_name = payload.get("agent_name", "")
        is_approved = decision["status"] == "approved"
        default_reason = "Approved from hookAgent GUI." if is_approved else "Denied from hookAgent GUI."
        reason = decision["reason"] or default_reason

        if hook_event_name == "BeforeTool" or agent_name == "gemini-cli":
            if is_approved:
                return {"decision": "allow", "reason": reason}
            return {
                "decision": "block",
                "reason": reason,
            }

        if hook_event_name == "PreToolUse":
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow" if is_approved else "deny",
                    "permissionDecisionReason": reason,
                }
            }

        return {}

    def _handle_approval_decision(self, approval_id: str) -> None:
        payload = self._read_json_body()
        status = payload.get("status")
        reason = payload.get("reason", "").strip()
        try:
            approval = STORE.decide_approval(approval_id, status, reason)
        except ValueError as exc:
            json_response(self, {"error": str(exc)}, status=400)
            return
        if approval is None:
            json_response(self, {"error": "Approval not found"}, status=404)
            return
        json_response(self, approval)

    def _serve_event_stream(self) -> None:
        queue = STORE.register_listener()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(b"event: ready\ndata: {}\n\n")
            self.wfile.flush()
            while True:
                while queue:
                    item = queue.popleft()
                    frame = f"event: {item['type']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
                    self.wfile.write(frame.encode("utf-8"))
                    self.wfile.flush()
                time.sleep(0.5)
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            STORE.unregister_listener(queue)


def run() -> None:
    server = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), HookAgentHandler)
    print(f"hookAgent server listening on http://{SERVER_HOST}:{SERVER_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
