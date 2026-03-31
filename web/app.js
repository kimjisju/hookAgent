const state = {
  sessions: [],
  approvals: [],
  selectedSessionId: null,
  sessionDetail: null,
};

const elements = {
  sessions: document.getElementById("sessions"),
  approvals: document.getElementById("approvals"),
  approvalCount: document.getElementById("approval-count"),
  sessionTitle: document.getElementById("session-title"),
  sessionMeta: document.getElementById("session-meta"),
  timeline: document.getElementById("timeline"),
  refresh: document.getElementById("refresh"),
};

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

function formatTime(value) {
  try {
    return new Date(value).toLocaleString();
  } catch (_) {
    return value;
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function loadSessions() {
  const payload = await fetchJson("/api/sessions");
  state.sessions = payload.sessions;
  renderSessions();
  if (!state.selectedSessionId && state.sessions.length) {
    state.selectedSessionId = state.sessions[0].session_id;
  }
  if (state.selectedSessionId) {
    await loadSessionDetail(state.selectedSessionId);
  }
}

async function loadSessionDetail(sessionId) {
  const detail = await fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
  state.selectedSessionId = sessionId;
  state.sessionDetail = detail;
  renderSessions();
  renderTimeline();
}

async function loadApprovals() {
  const payload = await fetchJson("/api/approvals");
  state.approvals = payload.approvals;
  renderApprovals();
}

function renderSessions() {
  if (!state.sessions.length) {
    elements.sessions.className = "stack empty";
    elements.sessions.textContent = "세션이 없습니다.";
    return;
  }
  elements.sessions.className = "stack";
  elements.sessions.innerHTML = "";
  for (const session of state.sessions) {
    const card = document.createElement("article");
    card.className = `session-card${session.session_id === state.selectedSessionId ? " active" : ""}`;
    card.innerHTML = `
      <h3>${session.summary || session.session_id}</h3>
      <div class="meta-row">
        <span class="pill">${session.agent_name || "unknown agent"}</span>
        <span class="pill">${session.status}</span>
        <span class="pill">${session.permission_mode || "unknown"}</span>
        <span class="pill">events ${session.event_count}</span>
        <span class="pill">pending ${session.pending_approvals}</span>
      </div>
      <p class="muted">${session.cwd || "cwd 없음"}</p>
      <p class="muted">${formatTime(session.updated_at)}</p>
    `;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "열기";
    button.addEventListener("click", () => loadSessionDetail(session.session_id));
    card.appendChild(button);
    elements.sessions.appendChild(card);
  }
}

function renderApprovals() {
  elements.approvalCount.textContent = String(state.approvals.length);
  if (!state.approvals.length) {
    elements.approvals.className = "stack empty";
    elements.approvals.textContent = "대기 중인 도구 요청이 없습니다.";
    return;
  }
  elements.approvals.className = "stack";
  elements.approvals.innerHTML = "";
  for (const approval of state.approvals) {
    const card = document.createElement("article");
    card.className = "approval-card";
    card.innerHTML = `
      <header>
        <strong>${approval.tool_name || "Unknown Tool"}</strong>
        <span class="pill">${formatTime(approval.created_at)}</span>
      </header>
      <p class="muted">${approval.session_id}</p>
      <pre>${formatJson(approval.tool_input)}</pre>
    `;
    const actions = document.createElement("div");
    actions.className = "actions";
    const allow = document.createElement("button");
    allow.type = "button";
    allow.textContent = "Yes";
    allow.addEventListener("click", () => submitDecision(approval.approval_id, "approved"));
    const deny = document.createElement("button");
    deny.type = "button";
    deny.className = "danger";
    deny.textContent = "No";
    deny.addEventListener("click", () => submitDecision(approval.approval_id, "denied"));
    actions.append(allow, deny);
    card.appendChild(actions);
    elements.approvals.appendChild(card);
  }
}

function summarizeEvent(event) {
  const raw = event.raw || {};
  if (event.hook_event_name === "UserPromptSubmit") {
    return raw.prompt || "";
  }
  if (event.hook_event_name === "Notification") {
    return formatJson({
      message: raw.message,
      notification_type: raw.notification_type,
      tool_name: raw.tool_name,
      tool_input: raw.tool_input,
      details: raw.details,
    });
  }
  if (event.hook_event_name === "Stop") {
    return raw.last_assistant_message || "";
  }
  if (raw.tool_input || raw.tool_response) {
    return formatJson({
      tool_input: raw.tool_input,
      tool_response: raw.tool_response,
    });
  }
  return formatJson(raw);
}

function renderTimeline() {
  const detail = state.sessionDetail;
  if (!detail) {
    elements.sessionTitle.textContent = "세션을 선택하세요";
    elements.sessionMeta.textContent = "실시간 타임라인이 여기에 표시됩니다.";
    elements.timeline.className = "timeline empty";
    elements.timeline.textContent = "아직 표시할 이벤트가 없습니다.";
    return;
  }
  elements.sessionTitle.textContent = detail.summary || detail.session_id;
  elements.sessionMeta.textContent = `${detail.agent_name || "unknown agent"} · ${detail.cwd || "cwd 없음"} · ${detail.permission_mode || "mode 없음"} · ${detail.status}`;
  if (!detail.events.length) {
    elements.timeline.className = "timeline empty";
    elements.timeline.textContent = "아직 표시할 이벤트가 없습니다.";
    return;
  }
  elements.timeline.className = "timeline";
  elements.timeline.innerHTML = "";
  for (const event of [...detail.events].reverse()) {
    const item = document.createElement("article");
    item.className = "timeline-item";
    item.innerHTML = `
      <header>
        <span class="kind">${event.hook_event_name}</span>
        <span class="pill">${formatTime(event.timestamp)}</span>
      </header>
      <p class="muted">${event.tool_name || rawToolName(event) || "session event"}</p>
      <pre>${summarizeEvent(event)}</pre>
    `;
    elements.timeline.appendChild(item);
  }
}

function rawToolName(event) {
  const raw = event.raw || {};
  if (typeof raw.tool_name === "string" && raw.tool_name) {
    return raw.tool_name;
  }
  if (raw.details && typeof raw.details.title === "string") {
    return raw.details.title;
  }
  return "";
}

async function submitDecision(approvalId, status) {
  await fetchJson(`/api/approvals/${approvalId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      status,
      reason: status === "approved" ? "Approved in hookAgent GUI." : "Denied in hookAgent GUI.",
    }),
  });
  await Promise.all([loadApprovals(), loadSessions()]);
}

function connectStream() {
  const source = new EventSource("/api/events/stream");
  source.addEventListener("event", async () => {
    await loadSessions();
  });
  source.addEventListener("approval_created", async () => {
    await Promise.all([loadApprovals(), loadSessions()]);
  });
  source.addEventListener("approval_updated", async () => {
    await Promise.all([loadApprovals(), loadSessions()]);
  });
  source.onerror = () => {
    source.close();
    setTimeout(connectStream, 1500);
  };
}

elements.refresh.addEventListener("click", async () => {
  await Promise.all([loadApprovals(), loadSessions()]);
});

Promise.all([loadApprovals(), loadSessions()]).then(connectStream);
