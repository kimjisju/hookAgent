from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalWaiter:
    condition: threading.Condition
    status: str = "pending"
    reason: str = ""
    decided_at: str | None = None


class EventStore:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.log_dir / "hook_agent_events.jsonl"
        self.approvals_file = self.log_dir / "hook_agent_approvals.jsonl"
        self.lock = threading.RLock()
        self.sessions: dict[str, dict[str, Any]] = {}
        self.event_history: deque[dict[str, Any]] = deque(maxlen=500)
        self.event_sequence = 0
        self.listeners: list[deque[dict[str, Any]]] = []
        self.approvals: dict[str, dict[str, Any]] = {}
        self.waiters: dict[str, ApprovalWaiter] = {}

    def _next_event_id(self) -> int:
        self.event_sequence += 1
        return self.event_sequence

    def _session_record(self, session_id: str) -> dict[str, Any]:
        record = self.sessions.get(session_id)
        if record is None:
            record = {
                "session_id": session_id,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
                "agent_name": "",
                "cwd": "",
                "permission_mode": "",
                "status": "active",
                "summary": "",
                "events": [],
                "pending_approvals": [],
            }
            self.sessions[session_id] = record
        return record

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _broadcast(self, payload: dict[str, Any]) -> None:
        for queue in list(self.listeners):
            queue.append(payload)

    def register_listener(self) -> deque[dict[str, Any]]:
        queue: deque[dict[str, Any]] = deque()
        with self.lock:
            self.listeners.append(queue)
        return queue

    def unregister_listener(self, queue: deque[dict[str, Any]]) -> None:
        with self.lock:
            self.listeners = [item for item in self.listeners if item is not queue]

    def add_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            session_id = payload.get("session_id") or "unknown-session"
            event = {
                "id": self._next_event_id(),
                "timestamp": utc_now_iso(),
                "session_id": session_id,
                "agent_name": payload.get("agent_name", ""),
                "hook_event_name": payload.get("hook_event_name", "Unknown"),
                "cwd": payload.get("cwd", ""),
                "permission_mode": payload.get("permission_mode", ""),
                "tool_name": payload.get("tool_name"),
                "tool_use_id": payload.get("tool_use_id"),
                "raw": payload,
            }
            session = self._session_record(session_id)
            session["updated_at"] = event["timestamp"]
            session["agent_name"] = payload.get("agent_name", session["agent_name"])
            session["cwd"] = payload.get("cwd", session["cwd"])
            session["permission_mode"] = payload.get("permission_mode", session["permission_mode"])
            if event["hook_event_name"] in {"UserPromptSubmit", "BeforeAgent", "PreToolUse", "BeforeTool"}:
                session["status"] = "active"
            if event["hook_event_name"] == "Stop":
                session["status"] = "stopped"
                session["summary"] = payload.get("last_assistant_message", "")
            elif event["hook_event_name"] == "SessionEnd":
                session["status"] = "ended"
            elif event["hook_event_name"] == "Notification":
                session["summary"] = payload.get("message", session["summary"])
            elif event["hook_event_name"] == "UserPromptSubmit":
                session["summary"] = payload.get("prompt", session["summary"])
            elif event["hook_event_name"] == "BeforeAgent":
                session["summary"] = payload.get("prompt", session["summary"])
            elif event["hook_event_name"] == "AfterAgent":
                session["status"] = "idle"
            session["events"].append(event)
            self.event_history.append(event)
            self._append_jsonl(self.events_file, event)
            self._broadcast({"type": "event", "data": event})
            return deepcopy(event)

    def create_approval(self, event: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            approval_id = str(uuid.uuid4())
            created_at = utc_now_iso()
            approval = {
                "approval_id": approval_id,
                "session_id": event["session_id"],
                "agent_name": event.get("agent_name", ""),
                "event_id": event["id"],
                "tool_name": event.get("tool_name"),
                "tool_use_id": event.get("tool_use_id"),
                "tool_input": event["raw"].get("tool_input", {}),
                "status": "pending",
                "reason": "",
                "created_at": created_at,
                "decided_at": None,
            }
            session = self._session_record(event["session_id"])
            session["pending_approvals"].append(approval_id)
            self.approvals[approval_id] = approval
            waiter = ApprovalWaiter(condition=threading.Condition(self.lock))
            self.waiters[approval_id] = waiter
            self._append_jsonl(self.approvals_file, approval)
            self._broadcast({"type": "approval_created", "data": approval})
            return deepcopy(approval)

    def decide_approval(self, approval_id: str, status: str, reason: str) -> dict[str, Any] | None:
        if status not in {"approved", "denied"}:
            raise ValueError(f"Unsupported approval status: {status}")
        with self.lock:
            approval = self.approvals.get(approval_id)
            if approval is None:
                return None
            if approval["status"] != "pending":
                return deepcopy(approval)
            approval["status"] = status
            approval["reason"] = reason
            approval["decided_at"] = utc_now_iso()
            session = self._session_record(approval["session_id"])
            session["pending_approvals"] = [
                item for item in session["pending_approvals"] if item != approval_id
            ]
            waiter = self.waiters.get(approval_id)
            if waiter is not None:
                waiter.status = status
                waiter.reason = reason
                waiter.decided_at = approval["decided_at"]
                waiter.condition.notify_all()
            self._append_jsonl(self.approvals_file, approval)
            self._broadcast({"type": "approval_updated", "data": approval})
            return deepcopy(approval)

    def wait_for_approval(self, approval_id: str, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        with self.lock:
            approval = self.approvals.get(approval_id)
            waiter = self.waiters.get(approval_id)
            if approval is None or waiter is None:
                return {"status": "approved", "reason": "Approval request missing; failing open."}
            while waiter.status == "pending":
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    approval["status"] = "denied"
                    approval["reason"] = "Approval timed out."
                    approval["decided_at"] = utc_now_iso()
                    session = self._session_record(approval["session_id"])
                    session["pending_approvals"] = [
                        item for item in session["pending_approvals"] if item != approval_id
                    ]
                    self._append_jsonl(self.approvals_file, approval)
                    self._broadcast({"type": "approval_updated", "data": approval})
                    return {"status": "denied", "reason": approval["reason"]}
                waiter.condition.wait(timeout=remaining)
            return {"status": waiter.status, "reason": waiter.reason}

    def get_sessions_summary(self) -> list[dict[str, Any]]:
        with self.lock:
            items = []
            for session in self.sessions.values():
                items.append(
                    {
                        "session_id": session["session_id"],
                        "created_at": session["created_at"],
                        "updated_at": session["updated_at"],
                        "agent_name": session["agent_name"],
                        "cwd": session["cwd"],
                        "permission_mode": session["permission_mode"],
                        "status": session["status"],
                        "summary": session["summary"],
                        "pending_approvals": len(session["pending_approvals"]),
                        "event_count": len(session["events"]),
                    }
                )
            items.sort(key=lambda item: item["updated_at"], reverse=True)
            return items

    def get_session_detail(self, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                return None
            detail = deepcopy(session)
            detail["approvals"] = [
                deepcopy(self.approvals[approval_id])
                for approval_id in detail["pending_approvals"]
                if approval_id in self.approvals
            ]
            return detail

    def get_all_pending_approvals(self) -> list[dict[str, Any]]:
        with self.lock:
            items = [deepcopy(item) for item in self.approvals.values() if item["status"] == "pending"]
            items.sort(key=lambda item: item["created_at"])
            return items
