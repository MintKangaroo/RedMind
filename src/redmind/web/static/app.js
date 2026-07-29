const byId = (id) => document.getElementById(id);
const state = {
  runs: [],
  current: null,
  meta: null,
  query: "",
  requestSequence: 0,
};
const TOKEN_KEY = "redmind.observer.token";

class RequestError extends Error {
  constructor(status) {
    super(`request failed with ${status}`);
    this.status = status;
  }
}

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#039;",
}[character]));

const formatDuration = (value) => {
  if (value >= 60_000) return `${(value / 60_000).toFixed(1)}m`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}s`;
  return `${value}ms`;
};

const formatNumber = (value) => Number(value).toLocaleString("ko-KR");
const formatDate = (value) => new Intl.DateTimeFormat("ko-KR", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "Asia/Seoul",
}).format(new Date(value));

const stateTone = (value) => ({
  completed: "success",
  approved: "success",
  executing: "running",
  waiting_approval: "warning",
  rejected: "danger",
  failed: "danger",
  cancelled: "muted",
}[value] || "muted");

const stateLabel = (value) => ({
  completed: "COMPLETED",
  approved: "APPROVED",
  executing: "EXECUTING",
  waiting_approval: "WAITING",
  rejected: "REJECTED",
  failed: "FAILED",
  cancelled: "CANCELLED",
}[value] || String(value).toUpperCase());

function showToast(message, tone = "success") {
  const toast = byId("toast");
  toast.textContent = message;
  toast.className = `toast visible ${tone}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.className = "toast";
  }, 2_800);
}

function accessToken() {
  return window.sessionStorage.getItem(TOKEN_KEY) || "";
}

function updateAccessStatus() {
  const enabled = Boolean(state.meta?.authentication_required);
  const connected = !enabled || Boolean(accessToken());
  byId("access-button").classList.toggle("connected", connected);
  byId("access-label").textContent = enabled ? (connected ? "ACCESS SET" : "SIGN IN") : "LOCAL";
}

function openAccessDialog(message) {
  if (!state.meta?.authentication_required) return;
  byId("access-message").textContent = message
    || "발급받은 Viewer 또는 Auditor bearer token을 입력하세요. Token은 현재 브라우저 탭의 session storage에만 보관됩니다.";
  byId("access-token").value = "";
  if (!byId("access-dialog").open) byId("access-dialog").showModal();
  window.setTimeout(() => byId("access-token").focus(), 50);
}

async function fetchJson(path, { authenticated = true } = {}) {
  const headers = { Accept: "application/json" };
  const token = accessToken();
  if (authenticated && token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, {
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401) {
      openAccessDialog("Token이 없거나 유효하지 않습니다. Viewer 또는 Auditor token을 다시 입력하세요.");
    }
    throw new RequestError(response.status);
  }
  return response.json();
}

function downloadJson(payload, filename) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function renderRunNavigation(selectedId) {
  const select = byId("run-select");
  select.innerHTML = state.runs.map((run) => `
    <option value="${run.id}" ${run.id === selectedId ? "selected" : ""}>
      ${escapeHtml(stateLabel(run.state))} · ${escapeHtml(run.objective)}
    </option>
  `).join("");

  byId("run-count").textContent = state.runs.length;
  byId("recent-runs").innerHTML = state.runs.map((run) => `
    <button class="recent-run ${run.id === selectedId ? "active" : ""}" type="button" data-run-id="${run.id}">
      <span class="run-dot ${stateTone(run.state)}"></span>
      <span>
        <strong>${escapeHtml(run.objective)}</strong>
        <small>${escapeHtml(stateLabel(run.state))} · ${formatDate(run.started_at)}</small>
      </span>
      <em>${run.progress_percent}%</em>
    </button>
  `).join("");

  document.querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", () => selectRun(button.dataset.runId));
  });
}

function renderTimeline(steps) {
  const normalizedQuery = state.query.trim().toLocaleLowerCase("ko-KR");
  const visibleSteps = normalizedQuery
    ? steps.filter((step) => [
      step.agent_name,
      step.title,
      step.detail,
      step.state,
    ].some((value) => value.toLocaleLowerCase("ko-KR").includes(normalizedQuery)))
    : steps;

  byId("timeline-result-count").textContent = `${visibleSteps.length} / ${steps.length} STEPS`;
  if (!visibleSteps.length) {
    byId("timeline").innerHTML = `
      <div class="empty-state">
        <span>⌕</span><strong>일치하는 실행 단계가 없습니다</strong>
        <p>다른 Agent 이름이나 단계 설명으로 검색해 보세요.</p>
      </div>`;
    return;
  }

  byId("timeline").innerHTML = visibleSteps.map((step, index) => {
    const tone = stateTone(step.state);
    return `
      <article class="step ${tone}" style="--step-index: ${index}">
        <div class="step-rail">
          <span class="step-number">${String(step.sequence).padStart(2, "0")}</span>
          <i></i>
        </div>
        <div class="step-body">
          <div class="step-heading">
            <div>
              <span class="step-agent">${escapeHtml(step.agent_name)}</span>
              <h3>${escapeHtml(step.title)}</h3>
            </div>
            <span class="step-status ${tone}"><i></i>${escapeHtml(stateLabel(step.state))}</span>
          </div>
          <p>${escapeHtml(step.detail)}</p>
          <div class="step-footer">
            <time>${formatDate(step.occurred_at)} KST</time>
            <span>${formatDuration(step.duration_ms)}</span>
            <span>TRACE #${String(step.sequence).padStart(3, "0")}</span>
          </div>
        </div>
      </article>`;
  }).join("");
}

function renderApprovals(approvals) {
  byId("approval-nav-count").textContent = approvals.length;
  if (!approvals.length) {
    byId("approval").innerHTML = `
      <div class="empty-compact">
        <span>—</span>
        <p>이 실행에는 승인 요청이 없습니다.</p>
      </div>`;
    return;
  }

  byId("approval").innerHTML = approvals.map((approval) => {
    const tone = stateTone(approval.status);
    return `
      <article class="approval-card">
        <div class="approval-status ${tone}">
          <span><i></i>${escapeHtml(stateLabel(approval.status))}</span>
          <code>${escapeHtml(approval.request_id)}</code>
        </div>
        <dl>
          <div><dt>ACTION</dt><dd>${escapeHtml(approval.action_type)}</dd></div>
          <div><dt>REVIEWER</dt><dd>${escapeHtml(approval.reviewer || "—")}</dd></div>
          <div><dt>EXPIRES</dt><dd>${formatDate(approval.expires_at)} KST</dd></div>
        </dl>
        <p>${escapeHtml(approval.reason || "검토 사유가 기록되지 않았습니다.")}</p>
      </article>`;
  }).join("");
}

function renderTools(tools) {
  byId("tool-count").textContent = tools.length;
  if (!tools.length) {
    byId("tools").innerHTML = `
      <div class="empty-compact"><span>—</span><p>정책 차단으로 실행된 Tool Call이 없습니다.</p></div>`;
    return;
  }

  byId("tools").innerHTML = tools.map((tool, index) => `
    <article class="tool">
      <span class="tool-index">${String(index + 1).padStart(2, "0")}</span>
      <div>
        <strong>${escapeHtml(tool.name)}</strong>
        <small>${escapeHtml(tool.category)} / ${escapeHtml(tool.permission)}</small>
      </div>
      <em class="${stateTone(tool.outcome)}"><i></i>${escapeHtml(stateLabel(tool.outcome))}</em>
      <time>${formatDuration(tool.duration_ms)}</time>
    </article>
  `).join("");
}

function renderEvidence(evidence) {
  byId("evidence-count").textContent = evidence.length;
  byId("evidence-metric").textContent = String(evidence.length).padStart(2, "0");
  if (!evidence.length) {
    byId("evidence").innerHTML = `
      <div class="empty-state compact-empty">
        <span>◇</span><strong>수집된 Evidence 없음</strong>
        <p>실행 전에 정책이 제안을 안전하게 차단했습니다.</p>
      </div>`;
    return;
  }

  byId("evidence").innerHTML = evidence.map((item, index) => `
    <article class="evidence-item">
      <div class="evidence-sequence">${String(index + 1).padStart(2, "0")}</div>
      <div class="evidence-body">
        <div>
          <span class="evidence-type">${escapeHtml(item.evidence_type)}</span>
          <span class="trust-badge">UNTRUSTED · VALIDATED</span>
        </div>
        <strong>${escapeHtml(item.summary)}</strong>
        <p><code>${escapeHtml(item.source)}</code><time>${formatDate(item.occurred_at)} KST</time></p>
      </div>
    </article>
  `).join("");
}

function renderReport(report, runState) {
  const groups = [
    ["fact", "확인된 사실", "FACT", report.facts],
    ["inference", "분석적 추론", "INFERENCE", report.inferences],
    ["unverified", "미검증 항목", "UNVERIFIED", report.unverified],
    ["recommendation", "권고 조치", "NEXT ACTION", report.recommendations],
  ];
  byId("report-state").innerHTML = runState === "executing"
    ? "<i></i> DRAFT"
    : "<i></i> READY";
  byId("report-state").className = `report-ready ${runState === "executing" ? "draft" : ""}`;
  byId("report").innerHTML = groups.map(([type, title, label, items]) => `
    <article class="report-block ${type}">
      <header><span>${escapeHtml(label)}</span><b>${items.length}</b></header>
      <h3>${escapeHtml(title)}</h3>
      ${items.length
        ? items.map((item) => `<p><i></i>${escapeHtml(item)}</p>`).join("")
        : '<p class="empty-line">기록된 항목이 없습니다.</p>'}
    </article>
  `).join("");
}

function renderFailure(failure) {
  const banner = byId("failure-banner");
  banner.hidden = !failure;
  if (!failure) return;
  byId("failure-kind").textContent = failure.kind.replaceAll("_", " ").toUpperCase();
  byId("failure-message").textContent = failure.message;
  byId("failure-retry").textContent = failure.retryable ? "RETRYABLE" : "NOT RETRYABLE";
}

function renderDashboard(data) {
  const run = data.run;
  state.current = data;

  byId("objective").textContent = run.objective;
  byId("run-id").textContent = String(run.id).slice(0, 8).toUpperCase();
  byId("started-at").textContent = `${formatDate(run.started_at)} KST`;
  byId("run-state").className = `run-state ${stateTone(run.state)}`;
  byId("run-state").innerHTML = `<i></i> ${escapeHtml(stateLabel(run.state))}`;
  byId("progress").textContent = `${run.progress_percent}%`;
  byId("progress-bar").style.width = `${run.progress_percent}%`;
  byId("duration").textContent = formatDuration(run.duration_ms);
  byId("risk").textContent = run.risk_level.toUpperCase();
  byId("risk").className = `risk risk-${run.risk_level}`;
  byId("cost").textContent = `$${data.usage.estimated_cost_usd.toFixed(4)}`;

  const totalTokens = data.usage.input_tokens + data.usage.output_tokens;
  const completedSteps = data.steps.filter((step) => ["completed", "approved"].includes(step.state)).length;
  const uniqueAgents = new Set(data.steps.map((step) => step.agent_name)).size;
  const eventCount = data.steps.length + data.tool_calls.length + data.evidence.length + data.approvals.length;

  byId("tokens").textContent = `${formatNumber(totalTokens)} total tokens`;
  byId("progress-detail").textContent = `${completedSteps} / ${data.steps.length} steps completed`;
  byId("agent-count").textContent = uniqueAgents;
  byId("event-count").textContent = eventCount;
  byId("budget-label").textContent = `${data.usage.budget_percent}%`;
  byId("budget-bar").style.width = `${data.usage.budget_percent}%`;
  byId("input-tokens").textContent = formatNumber(data.usage.input_tokens);
  byId("output-tokens").textContent = formatNumber(data.usage.output_tokens);
  byId("trace-status").innerHTML = run.state === "executing"
    ? "<i></i> LIVE TRACE"
    : "<i></i> TRACE SEALED";

  renderTimeline(data.steps);
  renderApprovals(data.approvals);
  renderTools(data.tool_calls);
  renderEvidence(data.evidence);
  renderReport(data.report, run.state);
  renderFailure(data.failure);

  byId("export-button").disabled = false;
  byId("last-sync").textContent = `${new Date().toLocaleTimeString("en-GB", {
    hour12: false,
    timeZone: "Asia/Seoul",
  })} KST`;
  renderRunNavigation(run.id);
}

function setLoading(isLoading) {
  byId("refresh-button").classList.toggle("spinning", isLoading);
  byId("refresh-button").disabled = isLoading;
  byId("run-select").disabled = isLoading;
}

async function selectRun(runId, notify = false) {
  const sequence = ++state.requestSequence;
  setLoading(true);
  try {
    const data = await fetchJson(`/api/v1/runs/${encodeURIComponent(runId)}`);
    if (sequence !== state.requestSequence) return;
    renderDashboard(data);
    const url = new URL(window.location.href);
    url.searchParams.set("run", runId);
    window.history.replaceState({}, "", url);
    if (notify) showToast("최신 실행 trace를 불러왔습니다.");
  } catch (error) {
    if (sequence !== state.requestSequence) return;
    byId("timeline").innerHTML = `
      <div class="empty-state error-state">
        <span>!</span><strong>타임라인을 불러오지 못했습니다</strong>
        <p>API 연결을 확인한 뒤 새로고침해 주세요.</p>
      </div>`;
    showToast(
      error instanceof RequestError && error.status === 401
        ? "접근 Token을 확인해 주세요."
        : "실행 정보를 불러오지 못했습니다.",
      "danger",
    );
  } finally {
    if (sequence === state.requestSequence) setLoading(false);
  }
}

async function loadRuns({ preserveSelection = true, notify = false } = {}) {
  setLoading(true);
  try {
    state.runs = await fetchJson("/api/v1/runs");
    byId("api-health").className = "api-health healthy";
    byId("api-health").innerHTML = "<i></i> API HEALTHY";
    if (!state.runs.length) throw new Error("no runs available");

    const queryRun = new URLSearchParams(window.location.search).get("run");
    const currentId = preserveSelection ? state.current?.run.id : null;
    const selectedId = [currentId, queryRun]
      .find((candidate) => state.runs.some((run) => run.id === candidate))
      || state.runs[0].id;
    renderRunNavigation(selectedId);
    await selectRun(selectedId, notify);
  } catch (error) {
    const accessFailure = error instanceof RequestError && [401, 403].includes(error.status);
    byId("api-health").className = `api-health ${accessFailure ? "" : "unhealthy"}`;
    byId("api-health").innerHTML = accessFailure
      ? "<i></i> ACCESS REQUIRED"
      : "<i></i> API OFFLINE";
    byId("timeline").innerHTML = `
      <div class="empty-state error-state">
        <span>!</span><strong>${accessFailure ? "보호된 실행 기록입니다" : "RedMind API에 연결할 수 없습니다"}</strong>
        <p>${accessFailure ? "우측 상단 SIGN IN에서 발급받은 Token을 입력하세요." : "서버 상태와 /health/live endpoint를 확인해 주세요."}</p>
      </div>`;
    showToast(accessFailure ? "접근 Token이 필요합니다." : "API 연결에 실패했습니다.", "danger");
    setLoading(false);
  }
}

async function exportAuditLog() {
  if (!state.current) return;
  const shortId = String(state.current.run.id).slice(0, 8);
  try {
    if (state.meta?.signed_exports) {
      const payload = await fetchJson(`/api/v1/runs/${encodeURIComponent(state.current.run.id)}/audit-export`);
      downloadJson(payload, `redmind-signed-audit-${shortId}.json`);
      showToast("서버 서명 감사 로그를 내보냈습니다.");
      return;
    }
    downloadJson({
      schema: "redmind.audit-export.v1",
      exported_at: new Date().toISOString(),
      read_only: true,
      ...state.current,
    }, `redmind-audit-${shortId}.json`);
    showToast("로컬 감사 로그 JSON을 내보냈습니다.");
  } catch (error) {
    if (error instanceof RequestError && error.status === 403) {
      openAccessDialog("서명 감사 파일에는 Auditor 역할이 필요합니다. Auditor token으로 다시 연결하세요.");
      showToast("Auditor 권한이 필요합니다.", "danger");
      return;
    }
    showToast("감사 로그를 내보내지 못했습니다.", "danger");
  }
}

async function boot() {
  try {
    state.meta = await fetchJson("/api/v1/meta", { authenticated: false });
    byId("observer-version").textContent = `v${state.meta.version}`;
    byId("environment-badge").innerHTML = state.meta.environment === "production"
      ? "<i></i> PROTECTED OPS"
      : "<i></i> AUTHORIZED LAB";
    if (state.meta.environment === "production") {
      byId("mode-label").innerHTML = "<i></i> DURABLE MODE";
      byId("mode-description").textContent = "PostgreSQL에 보존된 실행 trace를 역할 기반으로 조회하며 감사 파일은 서버에서 서명됩니다.";
    }
    updateAccessStatus();
    if (state.meta.authentication_required && !accessToken()) {
      openAccessDialog();
    }
    await loadRuns({ preserveSelection: false });
  } catch (error) {
    byId("api-health").className = "api-health unhealthy";
    byId("api-health").innerHTML = "<i></i> API OFFLINE";
    showToast("Observer metadata를 불러오지 못했습니다.", "danger");
  }
}

function setSidebar(open) {
  document.body.classList.toggle("sidebar-open", open);
  byId("menu-toggle").setAttribute("aria-expanded", String(open));
}

function updateClock() {
  byId("clock").textContent = `${new Date().toLocaleTimeString("en-GB", {
    hour12: false,
    timeZone: "Asia/Seoul",
  })} KST`;
}

byId("run-select").addEventListener("change", (event) => selectRun(event.target.value));
byId("timeline-search").addEventListener("input", (event) => {
  state.query = event.target.value;
  if (state.current) renderTimeline(state.current.steps);
});
byId("refresh-button").addEventListener("click", () => loadRuns({ notify: true }));
byId("export-button").addEventListener("click", exportAuditLog);
byId("access-button").addEventListener("click", () => {
  if (state.meta?.authentication_required) {
    openAccessDialog("현재 탭의 접근 Token을 교체하거나 지울 수 있습니다.");
  }
});
byId("access-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = byId("access-token").value.trim();
  if (!token) return;
  window.sessionStorage.setItem(TOKEN_KEY, token);
  updateAccessStatus();
  byId("access-dialog").close();
  await loadRuns({ preserveSelection: false, notify: true });
});
byId("clear-access").addEventListener("click", () => {
  window.sessionStorage.removeItem(TOKEN_KEY);
  state.current = null;
  updateAccessStatus();
  byId("access-token").value = "";
  showToast("현재 탭의 접근 Token을 지웠습니다.");
});
byId("access-cancel").addEventListener("click", () => byId("access-dialog").close());
byId("menu-toggle").addEventListener("click", () => {
  setSidebar(!document.body.classList.contains("sidebar-open"));
});
byId("sidebar-backdrop").addEventListener("click", () => setSidebar(false));
document.querySelectorAll(".primary-nav a").forEach((anchor) => {
  anchor.addEventListener("click", () => setSidebar(false));
});
document.addEventListener("keydown", (event) => {
  const activeTag = document.activeElement?.tagName;
  if (event.key === "/" && !["INPUT", "SELECT", "TEXTAREA"].includes(activeTag)) {
    event.preventDefault();
    byId("timeline-search").focus();
  }
  if (event.key === "Escape") {
    setSidebar(false);
    byId("timeline-search").blur();
  }
});

updateClock();
window.setInterval(updateClock, 1_000);
boot();
