from __future__ import annotations

import os
import signal
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SERVER_URL = os.environ.get("HOOK_AGENT_SERVER_URL", "http://127.0.0.1:8765")
GEMINI_EXTENSION_NAME = "gemini-auditor"
CLAUDE_PLUGIN_DIR = ROOT_DIR / "plugins" / "auditor"
GEMINI_EXTENSION_DIR = ROOT_DIR / "plugins" / GEMINI_EXTENSION_NAME
CODEX_PLUGIN_DIR = ROOT_DIR / "plugins" / "codex-auditor"
CODEX_PROJECT_DIR = ROOT_DIR / ".codex"


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
    path_sep = os.pathsep
    env["PYTHONPATH"] = str(ROOT_DIR) + (f"{path_sep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    env["HOOK_AGENT_SERVER_URL"] = env.get("HOOK_AGENT_SERVER_URL", DEFAULT_SERVER_URL)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    parsed = urlparse(env["HOOK_AGENT_SERVER_URL"])
    if parsed.hostname:
        env["HOOK_AGENT_HOST"] = env.get("HOOK_AGENT_HOST", parsed.hostname)
    if parsed.port:
        env["HOOK_AGENT_PORT"] = env.get("HOOK_AGENT_PORT", str(parsed.port))
    return env


def open_browser(server_url: str) -> None:
    try:
        if os.environ.get("HOOK_AGENT_OPEN_BROWSER", "1") == "0":
            return
        webbrowser.open(server_url, new=1)
    except Exception:
        # The control panel is optional; if opening a browser fails we still keep the agent running.
        return


def parse_agent(argv: list[str]) -> tuple[str, list[str]]:
    agent = "claude"
    remaining: list[str] = []
    idx = 0
    while idx < len(argv):
        current = argv[idx]
        if current == "--agent" and idx + 1 < len(argv):
            agent = argv[idx + 1]
            idx += 2
            continue
        remaining.append(current)
        idx += 1
    return agent, remaining


def build_agent_command(agent: str, extra_args: list[str]) -> list[str]:
    if agent == "claude":
        configured = os.environ.get("HOOK_AGENT_CLAUDE_BIN", "").strip()
        if configured:
            return [*split_command(configured), "--plugin-dir", str(CLAUDE_PLUGIN_DIR), *extra_args]
        return ["claude", "--plugin-dir", str(CLAUDE_PLUGIN_DIR), *extra_args]
    if agent == "gemini":
        configured = os.environ.get("HOOK_AGENT_GEMINI_BIN", "").strip()
        if configured:
            return [*split_command(configured), "--extensions", GEMINI_EXTENSION_NAME, *extra_args]
        return ["gemini", "--extensions", GEMINI_EXTENSION_NAME, *extra_args]
    if agent == "codex":
        configured = os.environ.get("HOOK_AGENT_CODEX_BIN", "").strip()
        if configured:
            return [*split_command(configured), *extra_args]
        return ["codex", *extra_args]
    raise ValueError(f"Unsupported agent: {agent}")


def split_command(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def resolve_agent_command(command: list[str]) -> list[str]:
    executable = shutil.which(command[0]) if len(command) == 1 or not Path(command[0]).exists() else command[0]
    if executable is not None:
        resolved = [executable, *command[1:]]
        if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
            return ["cmd.exe", "/c", executable, *command[1:]]
        return resolved
    raise FileNotFoundError(
        f"Could not find '{command[0]}' in PATH. Install it first or add it to PATH."
    )


def ensure_codex_project_files() -> None:
    CODEX_PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CODEX_PLUGIN_DIR / "config.toml", CODEX_PROJECT_DIR / "config.toml")
    shutil.copyfile(CODEX_PLUGIN_DIR / "hooks.json", CODEX_PROJECT_DIR / "hooks.json")


def main() -> int:
    env = build_server_env()
    server_url = env["HOOK_AGENT_SERVER_URL"]
    server_proc: subprocess.Popen[bytes] | None = None
    agent_proc: subprocess.Popen[bytes] | None = None
    agent, extra_args = parse_agent(sys.argv[1:])

    try:
        server_proc = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "scripts" / "hook_agent_server.py")],
            cwd=ROOT_DIR,
            env=env,
        )
        time.sleep(1)
        if server_proc.poll() is not None:
            return int(server_proc.returncode or 1)

        open_browser(server_url)

        if agent == "codex":
            if os.name == "nt":
                print(
                    "Codex hooks are not supported on Windows yet by Codex itself. "
                    "Use Linux or macOS for codex hook integration.",
                    file=sys.stderr,
                )
                return 1
            ensure_codex_project_files()

        agent_command = build_agent_command(agent, extra_args)
        agent_command = resolve_agent_command(agent_command)
        agent_proc = subprocess.Popen(
            agent_command,
            cwd=ROOT_DIR,
            env=env,
        )
        return agent_proc.wait()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        if agent_proc is not None and agent_proc.poll() is None:
            try:
                agent_proc.send_signal(signal.SIGINT)
                return agent_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        return 130
    finally:
        terminate_process(agent_proc)
        terminate_process(server_proc)


if __name__ == "__main__":
    raise SystemExit(main())
