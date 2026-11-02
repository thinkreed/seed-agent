/* seed-agent 桌面控制台（原生 ES 模块，无第三方依赖）。 */

const $ = (id) => document.getElementById(id);

const state = {
  ui: null,
  filter: "all",
  selected: null,
  lastEventSeq: 0,
  events: [],
  seenEvents: new Set(),
  loadingEvents: false,
  autoSelected: false,
};

const api = {
  async get(path) {
    const response = await fetch(path, { headers: { accept: "application/json" } });
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  },
  async post(body) {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`command: HTTP ${response.status}`);
    return response.json();
  },
};

function fmtTime(at) {
  if (!at) return "";
  return new Date(at * 1000).toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" });
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

function relativeTime(at) {
  if (!at) return "";
  const diff = Math.max(0, Math.round(Date.now() / 1000 - at));
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

/* ---------- state ---------- */

function applyState(ui) {
  state.ui = ui;
  $("status-dot").className = `dot ${ui.paused ? "paused" : "running"}`;
  $("status-text").textContent = ui.paused ? "已暂停" : "运行中";
  $("toggle-pause").textContent = ui.paused ? "恢复" : "暂停";
  $("seq").textContent = `seq ${ui.lastSeq}`;
  $("metrics").textContent = `${ui.counts.open} 进行中 · ${ui.counts.waitingPerson} 待人工`;

  $("count-all").textContent = String(ui.counts.total);
  $("count-waiting").textContent = String(ui.counts.waitingPerson);
  $("count-open").textContent = String(ui.counts.open);
  $("count-ended").textContent = String(ui.counts.ended);

  renderTickets();
  if (!state.selected && !state.autoSelected && ui.tickets.length > 0) {
    state.autoSelected = true;
    selectTicket(ui.tickets[0].id).catch((error) => console.error(error));
  }
  if (state.selected && !ui.tickets.some((ticket) => ticket.id === state.selected)) clearSelection();
}

function filteredTickets() {
  const tickets = state.ui?.tickets ?? [];
  if (state.filter === "waiting") return tickets.filter((ticket) => ticket.waitingPerson);
  if (state.filter === "open") return tickets.filter((ticket) => ticket.state === "open");
  if (state.filter === "ended") return tickets.filter((ticket) => ticket.state === "ended");
  return tickets;
}

function renderTickets() {
  const list = $("tickets");
  const tickets = filteredTickets();
  if (tickets.length === 0) {
    list.innerHTML = `<div class="empty" style="margin-top:18px;font-size:12px">没有匹配的工单</div>`;
    return;
  }
  list.innerHTML = tickets
    .map(
      (ticket) => `
      <button class="ticket ${ticket.id === state.selected ? "active" : ""}" data-id="${ticket.id}">
        <span class="source-dot ${ticket.source}"></span>
        <span>
          <span class="ticket-title-row">
            <span class="ticket-name">${escapeHtml(ticket.shortName)}</span>
            <span class="ticket-actor">${escapeHtml(ticket.source)}</span>
            <span class="ticket-time">${relativeTime(ticket.updatedAt)}</span>
          </span>
          <span class="ticket-text">${escapeHtml(ticket.title)}</span>
          <span class="ticket-sub">${escapeHtml(ticket.summary || ticket.stage)}</span>
        </span>
      </button>`,
    )
    .join("");
  for (const node of list.querySelectorAll(".ticket")) {
    node.addEventListener("click", () => selectTicket(node.dataset.id));
  }
}

/* ---------- ticket detail ---------- */

async function selectTicket(ticketId) {
  state.selected = ticketId;
  renderTickets();
  const view = await api.get(`/api/tickets/${encodeURIComponent(ticketId)}`);
  renderView(view);
}

function clearSelection() {
  state.selected = null;
  renderTickets();
  $("head-title").textContent = "选择一个工单";
  $("head-stage").textContent = "";
  $("head-stage").className = "chip";
  $("head-source").className = "source-dot";
  $("retry-btn").disabled = true;
  $("send-btn").disabled = true;
  $("timeline").innerHTML = `<div class="empty">从左侧选择一个工单，查看它的执行过程。</div>`;
}

function renderView(view) {
  const { ticket, timeline, mandate } = view;
  $("head-title").textContent = ticket.title || ticket.shortName;
  $("head-source").className = `source-dot ${ticket.source}`;
  const stage = $("head-stage");
  stage.textContent = ticket.state === "ended" ? "已结束" : ticket.stage;
  stage.className = `chip ${ticket.waitingPerson ? "person" : ""} ${ticket.state === "ended" ? "ended" : ""}`;
  $("retry-btn").disabled = false;
  $("send-btn").disabled = false;

  $("m-source").textContent = mandate.source;
  $("m-actor").textContent = mandate.actor || "—";
  $("m-scope").textContent = mandate.scope;
  $("m-strength").textContent = mandate.strength;
  $("m-policy").textContent = mandate.policyVersion || "—";

  const thread = $("timeline");
  if (timeline.length === 0) {
    thread.innerHTML = `<div class="empty">这个工单还没有事件。</div>`;
    return;
  }
  const rows = timeline.map(renderItem).join("");
  thread.innerHTML = `<div class="thread-inner">${rows}</div>`;
  thread.scrollTop = thread.scrollHeight;
}

function renderItem(item) {
  const time = `<span>${fmtTime(item.at)}</span>`;
  const who = `<span>${escapeHtml(item.who)}</span>`;
  if (item.kind === "trigger") {
    return `<div class="msg user"><div class="msg-body"><div class="msg-meta">${who}${time}</div><div class="msg-text">${escapeHtml(item.text)}</div></div></div>`;
  }
  if (item.kind === "message") {
    return `<div class="msg assistant"><div class="msg-avatar">✉</div><div class="msg-body"><div class="msg-meta">${who}${time}<span>· 已发送</span></div><div class="msg-text">${escapeHtml(item.text)}</div></div></div>`;
  }
  const failed = item.status === "failed" || item.status === "blocked";
  const cls = failed ? "msg error" : "msg tool";
  const icon = item.kind === "input" ? "⇢" : "✓";
  return `<div class="${cls}"><div class="msg-avatar">${icon}</div><div class="msg-body"><div class="msg-meta">${who}${time}<span>· ${escapeHtml(item.status ?? "")}</span></div><div class="msg-text">${escapeHtml(item.text)}</div></div></div>`;
}

/* ---------- events ---------- */

async function loadEvents() {
  if (state.loadingEvents) return;
  state.loadingEvents = true;
  try {
    const batch = await api.get(`/api/events?after=${state.lastEventSeq}&limit=200`);
    for (const event of batch) {
      if (event.type === "policy.changed") continue;
      if (state.seenEvents.has(event.seq)) continue;
      state.seenEvents.add(event.seq);
      state.events.push(event);
      state.lastEventSeq = Math.max(state.lastEventSeq, event.seq);
    }
  } finally {
    state.loadingEvents = false;
  }
  if (state.events.length > 300) state.events = state.events.slice(-300);
  $("events").innerHTML = state.events
    .slice(-200)
    .reverse()
    .map(
      (event) => `
      <div class="event">
        <span class="event-seq">${event.seq}</span>
        <span class="event-type" title="${escapeHtml(event.type)}">${escapeHtml(event.type)}</span>
      </div>`,
    )
    .join("");
  $("event-count").textContent = `${state.events.length}`;
}

/* ---------- live ---------- */

function connect() {
  const source = new EventSource("/api/stream");
  source.onmessage = async (message) => {
    try {
      const ui = JSON.parse(message.data);
      applyState(ui);
      await loadEvents();
      if (state.selected) {
        const view = await api.get(`/api/tickets/${encodeURIComponent(state.selected)}`);
        renderView(view);
      }
    } catch (error) {
      console.error(error);
    }
  };
  source.onerror = () => {
    $("status-dot").className = "dot";
    $("status-text").textContent = "连接断开，重试中…";
  };
}

/* ---------- interactions ---------- */

document.querySelector(".nav").addEventListener("click", (event) => {
  const button = event.target.closest(".nav-item");
  if (!button) return;
  state.filter = button.dataset.filter;
  for (const item of document.querySelectorAll(".nav-item")) item.classList.toggle("active", item === button);
  renderTickets();
});

$("toggle-pause").addEventListener("click", async () => {
  await api.post({ type: state.ui?.paused ? "resume" : "pause" });
});

$("retry-btn").addEventListener("click", async () => {
  if (state.selected) await api.post({ type: "retry", ticketId: state.selected });
});

$("focus-reply").addEventListener("click", () => $("reply-text").focus());

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = $("reply-text").value.trim();
  if (!state.selected || !text) return;
  $("reply-text").value = "";
  await api.post({ type: "reply", ticketId: state.selected, text });
});

$("theme-toggle").addEventListener("click", () => {
  const dark = !document.body.hasAttribute("data-ds-dark-theme");
  document.body.toggleAttribute("data-ds-dark-theme", dark);
  localStorage.setItem("seed-theme", dark ? "dark" : "light");
});

if (localStorage.getItem("seed-theme") === "dark") {
  document.body.setAttribute("data-ds-dark-theme", "");
}
$("send-btn").disabled = true;

api.get("/api/state").then(applyState).catch((error) => console.error(error));
loadEvents().catch((error) => console.error(error));
connect();