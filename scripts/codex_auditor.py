from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.request


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "..", "log", "codex_audit_log.txt")
SERVER_URL = os.environ.get("HOOK_AGENT_SERVER_URL", "http://127.0.0.1:8765")
EVENT_ENDPOINT = f"{SERVER_URL.rstrip('/')}/api/hook-event"
HTTP_TIMEOUT = int(os.environ.get("HOOK_AGENT_HTTP_TIMEOUT", "3700"))
AGENT_NAME = "codex"


def ensure_log_dir() -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def read_hook_input() -> object:
    raw = sys.stdin.buffer.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8", errors="surrogatepass"))


def write_raw_log(event_name: str, payload: dict[str, object]) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n=== [RAW INPUT: {event_name}] {timestamp} ===\n")
        fh.write(json.dumps(payload, indent=2, ensure_ascii=False))
        fh.write("\n")


def post_event(payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        EVENT_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def build_codex_response(event_name: str, hook_response: dict[str, object]) -> dict[str, object]:
    if event_name != "PreToolUse":
        return hook_response

    permission_decision = None
    permission_reason = None
    hook_specific_output = hook_response.get("hookSpecificOutput")
    if isinstance(hook_specific_output, dict):
        permission_decision = hook_specific_output.get("permissionDecision")
        permission_reason = hook_specific_output.get("permissionDecisionReason")

    if permission_decision in {"allow", "deny"}:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": permission_decision,
                "permissionDecisionReason": permission_reason or "",
            }
        }

    return {}


def emit_response(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.write("\n")


def main() -> None:
    ensure_log_dir()
    try:
        input_data = read_hook_input()
        if not isinstance(input_data, dict):
            emit_response({})
            return

        input_data["agent_name"] = AGENT_NAME
        event_name = str(input_data.get("hook_event_name", "Unknown"))
        write_raw_log(event_name, input_data)

        hook_response: dict[str, object] = {}
        try:
            payload = post_event(input_data)
            response = payload.get("hook_response", {})
            if isinstance(response, dict):
                hook_response = build_codex_response(event_name, response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError):
            hook_response = {}

        emit_response(hook_response)
    except Exception:
        emit_response({})


if __name__ == "__main__":
    main()
