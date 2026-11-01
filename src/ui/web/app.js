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
  const date = new Date(at * 1000);
  return date.toLocaleTimeString("zh-CN", { hour12: false });
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

/* ---------- state ---------- */

function applyState(ui) {
  state.ui = ui;
  $("status-dot").className = `dot ${ui.paused ? "paused" : "running"}`;
  $("status-text").textContent = ui.paused ? "已暂停" : "运行中";
  $("toggle-pause").textContent = ui.paused ? "恢复" : "暂停";
  $("seq").textContent = `seq ${ui.lastSeq}`;

  $("metrics").innerHTML = [
    metric("工单", ui.counts.total),
    metric("进行中", ui.counts.open),
    metric("待人工", ui.counts.waitingPerson),
  ].join("");

  renderTickets();
  if (!state.selected && !state.autoSelected && ui.tickets.length > 0) {
    state.autoSelected = true;
    selectTicket(ui.tickets[0].id).catch((error) => console.error(error));
  }
  if (state.selected) {
    const ownsSelection = ui.tickets.some((ticket) => ticket.id === state.selected);
    if (!ownsSelection) clearSelection();
  }
}

function metric(label, value) {
  return `<div class="metric"><b>${value}</b><span>${label}</span></div>`;
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
    list.innerHTML = `<div class="empty" style="margin-top:24px">没有匹配的工单</div>`;
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
            <span class="muted">${escapeHtml(ticket.source)}·${escapeHtml(ticket.actor.slice(0, 12))}</span>
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
  $("head-source").className = "source-dot";
  $("retry-btn").disabled = true;
  $("send-btn").disabled = true;
  $("timeline").innerHTML = `<div class="empty">从左侧选择一个工单，查看它的事件时间线。</div>`;
}

function renderView(view) {
  const { ticket, timeline, mandate } = view;
  $("head-title").textContent = ticket.title || ticket.shortName;
  $("head-source").className = `source-dot ${ticket.source}`;
  const stage = $("head-stage");
  stage.textContent = `${ticket.stage}${ticket.state === "ended" ? " · ended" : ""}`;
  stage.className = `stage ${ticket.waitingPerson ? "person" : ""} ${ticket.state === "ended" ? "ended" : ""}`;
  $("retry-btn").disabled = false;
  $("send-btn").disabled = false;

  $("m-source").textContent = mandate.source;
  $("m-actor").textContent = mandate.actor || "—";
  $("m-scope").textContent = mandate.scope;
  $("m-strength").textContent = mandate.strength;
  $("m-policy").textContent = mandate.policyVersion || "—";

  const timelineNode = $("timeline");
  if (timeline.length === 0) {
    timelineNode.innerHTML = `<div class="empty">这个工单还没有事件。</div>`;
    return;
  }
  timelineNode.innerHTML = timeline
    .map((item) => {
      const avatar = { trigger: "▣", input: "⇢", report: "✓", message: "✉" }[item.kind] ?? "·";
      return `
      <div class="item ${item.kind}">
        <div class="item-avatar">${avatar}</div>
        <div class="item-body">
          <div class="item-meta">
            <span>${escapeHtml(item.who)}</span>
            <span>${fmtTime(item.at)}</span>
            ${item.status ? `<span>· ${escapeHtml(item.status)}</span>` : ""}
          </div>
          <div class="item-text">${escapeHtml(item.text)}</div>
        </div>
      </div>`;
    })
    .join("");
  timelineNode.scrollTop = timelineNode.scrollHeight;
}

/* ---------- events ---------- */

async function loadEvents() {
  if (state.loadingEvents) return;
  state.loadingEvents = true;
  try {
    const batch = await api.get(`/api/events?after=${state.lastEventSeq}&limit=200`);
    for (const event of batch) {
      if (event.type === "policy.changed") continue; // 每次启动都会记录，噪声项不展示
      if (state.seenEvents.has(event.seq)) continue;
      state.seenEvents.add(event.seq);
      state.events.push(event);
      state.lastEventSeq = Math.max(state.lastEventSeq, event.seq);
    }
  } finally {
    state.loadingEvents = false;
  }
  if (state.events.length > 300) state.events = state.events.slice(-300);
  const node = $("events");
  node.innerHTML = state.events
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
  $("event-count").textContent = `${state.events.length} 条`;
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

$("filters").addEventListener("click", (event) => {
  const button = event.target.closest(".chip");
  if (!button) return;
  state.filter = button.dataset.filter;
  for (const chip of document.querySelectorAll(".chip")) chip.classList.toggle("active", chip === button);
  renderTickets();
});

$("toggle-pause").addEventListener("click", async () => {
  const type = state.ui?.paused ? "resume" : "pause";
  await api.post({ type });
});

$("retry-btn").addEventListener("click", async () => {
  if (!state.selected) return;
  await api.post({ type: "retry", ticketId: state.selected });
});

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = $("reply-text").value.trim();
  if (!state.selected || !text) return;
  $("reply-text").value = "";
  await api.post({ type: "reply", ticketId: state.selected, text });
});

$("theme-toggle").addEventListener("click", () => {
  const next = document.body.dataset.theme === "dark" ? "light" : "dark";
  document.body.dataset.theme = next;
  localStorage.setItem("seed-theme", next);
});

const saved = localStorage.getItem("seed-theme");
if (saved) document.body.dataset.theme = saved;

api.get("/api/state").then(applyState).catch((error) => console.error(error));
loadEvents().catch((error) => console.error(error));
connect();