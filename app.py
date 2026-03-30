from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SERVER_URL = os.environ.get("HOOK_AGENT_SERVER_URL", "http://127.0.0.1:8765")


def terminate_process(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def build_server_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR) + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    env["HOOK_AGENT_SERVER_URL"] = env.get("HOOK_AGENT_SERVER_URL", DEFAULT_SERVER_URL)
    parsed = urlparse(env["HOOK_AGENT_SERVER_URL"])
    if parsed.hostname:
        env["HOOK_AGENT_HOST"] = env.get("HOOK_AGENT_HOST", parsed.hostname)
    if parsed.port:
        env["HOOK_AGENT_PORT"] = env.get("HOOK_AGENT_PORT", str(parsed.port))
    return env


def main() -> int:
    env = build_server_env()
    server_url = env["HOOK_AGENT_SERVER_URL"]
    server_proc: subprocess.Popen[bytes] | None = None
    claude_proc: subprocess.Popen[bytes] | None = None

    try:
        server_proc = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "scripts" / "hook_agent_server.py")],
            cwd=ROOT_DIR,
            env=env,
        )
        time.sleep(1)
        if server_proc.poll() is not None:
            return int(server_proc.returncode or 1)

        subprocess.Popen(["open", server_url], cwd=ROOT_DIR)

        claude_proc = subprocess.Popen(
            ["claude", "--plugin-dir", "./plugins/auditor", *sys.argv[1:]],
            cwd=ROOT_DIR,
            env=env,
        )
        return claude_proc.wait()
    except KeyboardInterrupt:
        if claude_proc is not None and claude_proc.poll() is None:
            try:
                claude_proc.send_signal(signal.SIGINT)
                return claude_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        return 130
    finally:
        terminate_process(claude_proc)
        terminate_process(server_proc)


if __name__ == "__main__":
    raise SystemExit(main())
