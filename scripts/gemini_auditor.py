from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "..", "log", "gemini_audit_log.txt")
SERVER_URL = os.environ.get("HOOK_AGENT_SERVER_URL", "http://127.0.0.1:8765")
EVENT_ENDPOINT = f"{SERVER_URL.rstrip('/')}/api/hook-event"
HTTP_TIMEOUT = int(os.environ.get("HOOK_AGENT_HTTP_TIMEOUT", "3700"))
AGENT_NAME = "gemini-cli"
FAIL_CLOSED_EVENTS = {"BeforeTool"}
SURROGATE_PATTERN = re.compile(r"[\ud800-\udfff]")


def ensure_log_dir() -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return SURROGATE_PATTERN.sub("\uFFFD", value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(sanitize_value(key)): sanitize_value(item) for key, item in value.items()}
    return value


def write_raw_log(event_name: str, payload: dict[str, object]) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n=== [RAW INPUT: {event_name}] {timestamp} ===\n")
        fh.write(json.dumps(payload, indent=2, ensure_ascii=False))
        fh.write("\n")


def write_error_log(message: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"\n=== [ERROR] {timestamp} ===\n")
        fh.write(message)
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


def normalize_notification_payload(payload: dict[str, object]) -> None:
    if payload.get("hook_event_name") != "Notification":
        return
    if payload.get("notification_type") != "ToolPermission":
        return

    details = payload.get("details")
    if not isinstance(details, dict):
        return

    notification_type = details.get("type")
    if notification_type == "edit":
        payload["tool_name"] = "write_file"
        payload["tool_input"] = {
            "file_path": details.get("filePath") or details.get("fileName"),
            "original_content": details.get("originalContent"),
            "new_content": details.get("newContent"),
            "file_diff": details.get("fileDiff"),
        }
        return

    if notification_type == "exec":
        payload["tool_name"] = "run_shell_command"
        payload["tool_input"] = {
            "command": details.get("command"),
            "root_command": details.get("rootCommand"),
        }


def fail_closed_response(event_name: str, reason: str) -> dict[str, object]:
    if event_name in FAIL_CLOSED_EVENTS:
        return {
            "decision": "block",
            "reason": reason,
        }
    return {}


def emit_response(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.write("\n")


def read_hook_input() -> object:
    raw = sys.stdin.buffer.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8", errors="surrogatepass"))


def main() -> None:
    event_name = "Unknown"
    try:
        ensure_log_dir()
        input_data = read_hook_input()
        if not isinstance(input_data, dict):
            reason = "hookAgent received a non-object hook payload."
            write_error_log(reason)
            emit_response(fail_closed_response(event_name, reason))
            return

        input_data = sanitize_value(input_data)
        if not isinstance(input_data, dict):
            reason = "hookAgent could not sanitize hook payload."
            write_error_log(reason)
            emit_response(fail_closed_response(event_name, reason))
            return

        input_data["agent_name"] = AGENT_NAME
        normalize_notification_payload(input_data)
        event_name = str(input_data.get("hook_event_name", "Unknown"))
        write_raw_log(event_name, input_data)

        hook_response: dict[str, object] = {}
        try:
            payload = post_event(input_data)
            response = payload.get("hook_response", {})
            if isinstance(response, dict):
                hook_response = response
            elif event_name in FAIL_CLOSED_EVENTS:
                reason = "hookAgent returned an invalid response for a blocking hook."
                write_error_log(reason)
                hook_response = fail_closed_response(event_name, reason)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError):
            reason = f"hookAgent could not verify approval for {event_name}."
            write_error_log(reason)
            hook_response = fail_closed_response(event_name, reason)

        emit_response(hook_response)
    except Exception as exc:
        reason = f"hookAgent bridge failed: {exc}"
        write_error_log(reason)
        emit_response(fail_closed_response(event_name, reason))


if __name__ == "__main__":
    main()
