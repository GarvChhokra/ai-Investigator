const API = (
  new URLSearchParams(location.search).get("api") ||
  (location.protocol.startsWith("http") ? location.origin : "http://localhost:8000")
).replace(/\/$/, "");

const state = { cases: [], filter: "all", selectedId: null, detail: null, verdicts: {} };

const TIER_ORDER = ["High", "Medium", "Low", null];
const TIER_BLURB = {
  High: "genuinely suspicious",
  Medium: "worth a closer look",
  Low: "likely false positive",
  null: "not yet assessed",
};

/* ---------------- helpers ---------------- */
const $ = (s) => document.querySelector(s);
const usd = (n) => "$" + Number(n).toLocaleString("en-US");
const esc = (s) => {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
};
const timeAgo = (iso) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};
// minimal safe markdown for chat answers: escape, then **bold** and `code`
const md = (s) =>
  esc(s)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^\s*[-*]\s+/gm, "• ");

async function api(path, opts) {
  const res = await fetch(API + path, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts && opts.headers) },
  });
  if (!res.ok) throw new Error(res.status + " " + path);
  return res.json();
}

/* ---------------- queue ---------------- */
async function loadQueue() {
  try {
    const data = await api("/api/cases");
    state.cases = data.cases;
    renderStandup(data.counts);
    renderQueue();
  } catch {
    $("#queueList").innerHTML =
      `<div class="queue-empty">Can’t reach the backend at ${esc(API)}.<br>Is it running?</div>`;
  }
}

function renderStandup(c) {
  const items =
    c.assessed < c.total
      ? [[`${c.assessed} / ${c.total}`, "assessed", false]]
      : [
          [c.needs_review, "need review", c.needs_review > 0],
          [c.high_dollar, "above $20k", false],
          [c.disagreements, "rule/AI splits", false],
          [c.likely_benign, "likely benign", false],
        ];
  $("#standup").innerHTML = items
    .map(
      ([n, label, hot]) =>
        `<span class="item ${hot ? "hot" : ""}"><span class="n">${n}</span>${label}</span>`,
    )
    .join("");
  $("#assessQueueBtn").textContent = c.assessed === c.total ? "Re-assess queue" : "Assess queue";
}

function renderQueue() {
  const groups = {};
  for (const c of state.cases) (groups[c.effective_risk] ||= []).push(c);

  let html = "";
  for (const tier of TIER_ORDER) {
    let rows = groups[tier] || [];
    if (state.filter !== "all") rows = rows.filter((c) => c.effective_risk === state.filter);
    if (!rows.length) continue;
    rows.sort(
      (a, b) =>
        (b.assessment ? b.assessment.heuristic_score : -1) -
        (a.assessment ? a.assessment.heuristic_score : -1),
    );
    html += `<div class="queue-group">${tier || "Unassessed"} · ${rows.length} · ${TIER_BLURB[tier]}</div>`;
    html += rows.map(queueItem).join("");
  }
  const list = $("#queueList");
  list.innerHTML = html || `<div class="queue-empty">Nothing in this filter.</div>`;
  list.querySelectorAll(".queue-item").forEach((el) =>
    el.addEventListener("click", () => openCase(el.dataset.id)),
  );
}

function queueItem(c) {
  const a = c.assessment;
  const tier = c.effective_risk || "none";
  const score = a ? Math.round(a.heuristic_score) : "–";
  let mark = "";
  if (c.status === "RESOLVED") mark = '<span class="dot resolved" title="Resolved"></span>';
  else if (c.status === "UNDER_REVIEW") mark = '<span class="dot review" title="Under review"></span>';
  else if (a && a.disagreement) mark = '<span class="dot split" title="AI and rules disagree"></span>';
  return `
    <div class="queue-item tier-${tier} ${c.case_id === state.selectedId ? "selected" : ""}" data-id="${c.case_id}">
      <div class="qi-score">${score}</div>
      <div class="qi-body">
        <div class="qi-top"><span class="qi-id">${c.case_id}</span><span class="qi-amount">${usd(c.claim_amount_usd)}</span></div>
        <div class="qi-summary">${a ? esc(a.summary) : "Not assessed — open to run it"}</div>
        <div class="qi-meta">
          <span>${esc(c.care_type)} · ${esc(c.state)}</span>
          <span>${a ? esc(a.confidence.toLowerCase()) + " confidence" : ""}${mark}</span>
        </div>
      </div>
    </div>`;
}

$("#queueFilters").addEventListener("click", (e) => {
  const btn = e.target.closest(".filter-chip");
  if (!btn) return;
  document.querySelectorAll(".filter-chip").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  state.filter = btn.dataset.tier;
  renderQueue();
});

$("#assessQueueBtn").addEventListener("click", async () => {
  const btn = $("#assessQueueBtn");
  btn.disabled = true;
  btn.textContent = "Assessing…";
  try {
    await api("/api/assess/batch", { method: "POST" });
    await loadQueue();
    if (state.selectedId) await openCase(state.selectedId);
  } finally {
    btn.disabled = false;
  }
});

/* ---------------- case detail ---------------- */
async function openCase(id) {
  state.selectedId = id;
  state.verdicts = {};
  renderQueue();
  $("#detailPane").innerHTML = `<div class="empty">Loading ${esc(id)}…</div>`;
  try {
    const d = await api("/api/cases/" + id);
    state.detail = d;
    const last = d.decisions.at(-1);
    if (last?.indicator_verdicts) state.verdicts = { ...last.indicator_verdicts };
    renderDetail();
  } catch (e) {
    $("#detailPane").innerHTML = `<div class="error">Failed to load case.<br><span class="mono">${esc(e.message)}</span></div>`;
  }
}

function renderDetail() {
  const d = state.detail;
  const c = d.case;
  const a = d.assessment;
  if (!a) {
    $("#detailPane").innerHTML = `<div class="error">No assessment for this case yet.</div>`;
    return;
  }

  const tier = d.effective_risk || a.risk_level;
  const evById = Object.fromEntries(a.evidence.map((e) => [e.id, e]));
  const scored = a.evidence
    .filter((e) => e.category !== "context" && e.category !== "data_quality")
    .sort((x, y) => y.contribution - x.contribution);
  const dq = a.evidence.filter((e) => e.category === "data_quality");

  $("#detailPane").innerHTML = `
    <div class="detail-inner">
      <div class="case-head">
        <div>
          <div class="case-title">${c.case_id} · ${esc(c.claim_number)}</div>
          <div class="case-sub">${esc(c.care_type)}<span class="sep">·</span>${usd(c.claim_amount_usd)}<span class="sep">·</span>${esc(c.state)}<span class="sep">·</span>${esc(c.claim_date)}</div>
        </div>
        <div class="case-actions">
          <span class="risk-pill badge-${tier}">${a.risk_level}<span class="s">· ${Math.round(a.heuristic_score)}</span></span>
          <button class="link-btn" id="reassessBtn">Re-assess</button>
        </div>
      </div>

      <div class="section assessment">
        <div class="summary">${esc(a.summary)}</div>
        <div class="next"><b>Next step.</b> ${esc(a.recommended_action)}</div>
        ${a.disagreement ? `<div class="note-line warn">The AI says <b>${a.risk_level}</b>; the rule-based score says <b>${a.heuristic_band}</b> (${a.heuristic_score}/100). Both are shown — your call.</div>` : ""}
        ${!a.llm_used ? `<div class="note-line muted">Rules-only — the AI narrative was unavailable, so this reflects the deterministic score.</div>` : ""}
        <div class="meta">
          <span>${a.confidence} confidence</span>
          <span>Peer group: ${esc(a.peer_group)}</span>
        </div>
      </div>

      <div class="section">
        <h3>Key indicators</h3>
        ${a.key_indicators.map((k) => indicatorHtml(k, evById[k.evidence_id])).join("")}
        <details class="all-signals">
          <summary>Show all ${scored.length} signals vs peers</summary>
          ${scored.map(sigRow).join("")}
          ${dq.map((e) => `<div class="ind-detail"><b>Data quality —</b> ${esc(e.label)}</div>`).join("")}
        </details>
      </div>

      ${
        a.missing_info.length
          ? `<div class="section"><h3>Not verified by the AI</h3>
             <ul style="margin:0;padding-left:16px;line-height:1.7;color:var(--ink-soft)">
             ${a.missing_info.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>`
          : ""
      }

      <details class="record">
        <summary>Claim record</summary>
        <div class="record-grid">${recordRows(c)}</div>
      </details>

      <div class="box">
        <h3>Your decision</h3>
        <div class="field-label">Risk level</div>
        <select id="riskOverride">
          <option value="">Keep AI risk (${a.risk_level})</option>
          <option value="Low">Override → Low</option>
          <option value="Medium">Override → Medium</option>
          <option value="High">Override → High</option>
        </select>
        <div style="margin-top:10px"><textarea id="rationale" rows="2" placeholder="Rationale (optional)"></textarea></div>
        <div class="decide">
          <button class="primary" data-action="accept">Accept AI finding</button>
          <button data-action="reject">Reject — false positive</button>
          <button data-action="escalate">Escalate</button>
        </div>
        <div class="decide-status">${decideStatus(d)}</div>

        <div class="notes">
          ${d.notes.map((n) => `<div class="note">${esc(n.body)}<div class="m">${esc(n.actor)} · ${timeAgo(n.created_at)}</div></div>`).join("")}
          <div class="row-input">
            <input type="text" id="noteInput" placeholder="Add a note…" />
            <button class="btn" id="addNoteBtn">Add</button>
          </div>
        </div>
      </div>

      <div class="box">
        <h3>Ask about this case</h3>
        <div class="chat-hint">Grounded in this case’s data only — it won’t answer what isn’t there.</div>
        <div class="chips">
          <button class="chip">Why this risk level?</button>
          <button class="chip">Strongest single indicator?</button>
          <button class="chip">What would make this a false positive?</button>
        </div>
        <div class="chat-log" id="chatLog">
          ${d.chat.map((m) => `<div class="msg ${m.role}">${m.role === "assistant" ? md(m.content) : esc(m.content)}</div>`).join("")}
        </div>
        <div class="row-input">
          <input type="text" id="chatInput" placeholder="Ask a follow-up…" />
          <button class="btn" id="chatSendBtn">Send</button>
        </div>
      </div>
    </div>`;

  wireDetail();
}

function indicatorHtml(k, e) {
  const v = state.verdicts[k.evidence_id];
  return `
    <div class="ind" data-ev="${k.evidence_id}">
      <div class="ind-head">
        <span class="ind-caret">›</span>
        <div style="flex:1;min-width:0">
          <div class="ind-label">${esc(e ? e.label : k.evidence_id)}</div>
          <div class="ind-why">${esc(k.explanation)}</div>
          <div class="ind-detail" hidden>
            ${
              e
                ? `<span class="mono">value: ${esc(e.raw_value)}${e.unit ? " " + esc(e.unit) : ""}</span>${e.peer_context ? "<br>" + esc(e.peer_context) : ""}`
                : "no evidence record"
            }
          </div>
          <div class="ind-fb">
            <button class="fb ${v === "accept" ? "on-accept" : ""}" data-verdict="accept">Confirmed</button>
            <button class="fb ${v === "reject" ? "on-reject" : ""}" data-verdict="reject">Not relevant</button>
          </div>
        </div>
      </div>
    </div>`;
}

function sigRow(e) {
  const strength = e.weight > 0 ? Math.min(1, e.contribution / e.weight) : 0;
  const val =
    typeof e.raw_value === "number"
      ? (e.unit === "%" ? (e.raw_value > 0 ? "+" : "") + e.raw_value + "%" : e.raw_value + (e.unit ? " " + e.unit : ""))
      : e.raw_value;
  return `
    <div class="sig">
      <div class="sig-label" title="${esc(e.peer_context || "")}">${esc(e.label)}</div>
      <div class="sig-track"><div class="sig-fill" style="width:${Math.max(strength * 100, 2)}%"></div></div>
      <div class="sig-delta">${esc(val)}</div>
    </div>`;
}

function recordRows(c) {
  const f = [
    ["Care type", c.care_type],
    ["Amount", usd(c.claim_amount_usd)],
    ["State", c.state],
    ["Claim date", c.claim_date],
    ["Prior claims (12mo)", c.prior_claims_last_12mo],
    ["Weekly visits", c.weekly_visit_frequency],
    ["Member–provider distance", c.member_provider_distance_miles + " mi"],
    ["Amount vs peer avg", c.amount_vs_peer_avg_pct + "%"],
    ["Weekend billing ratio", c.weekend_billing_ratio],
    ["Round-dollar ratio", c.round_dollar_billing_ratio],
    ["Duplicate service billed", c.duplicate_service_billed ? "yes" : "no"],
    ["Shared contact w/ provider", c.shared_contact_with_provider ? "yes" : "no"],
    ["Service overlap (other provider)", c.service_overlap_other_provider ? "yes" : "no"],
    ["Recent policy change", c.recent_policy_change_flag ? "yes" : "no"],
  ];
  return f
    .map(([k, v]) => `<div class="row"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`)
    .join("");
}

function decideStatus(d) {
  const last = d.decisions.at(-1);
  if (!last) return "Not yet reviewed.";
  return `Last: <b>${esc(last.action)}</b>${last.risk_override ? " · risk → " + esc(last.risk_override) : ""} · ${timeAgo(last.created_at)}${last.rationale ? ` · “${esc(last.rationale)}”` : ""}`;
}

/* ---------------- detail wiring ---------------- */
function wireDetail() {
  const id = state.detail.case_id;

  $("#reassessBtn").addEventListener("click", async (ev) => {
    ev.target.disabled = true;
    ev.target.textContent = "Re-assessing…";
    await api("/api/assess/" + id + "?force=true", { method: "POST" });
    await openCase(id);
    await loadQueue();
  });

  document.querySelectorAll(".ind").forEach((row) => {
    const evId = row.dataset.ev;
    row.querySelector(".ind-head").addEventListener("click", (e) => {
      if (e.target.closest(".fb")) return;
      const box = row.querySelector(".ind-detail");
      box.hidden = !box.hidden;
      row.classList.toggle("open", !box.hidden);
    });
    row.querySelectorAll(".fb").forEach((btn) => {
      btn.addEventListener("click", () => {
        const v = btn.dataset.verdict;
        state.verdicts[evId] = state.verdicts[evId] === v ? undefined : v;
        if (!state.verdicts[evId]) delete state.verdicts[evId];
        row.querySelectorAll(".fb").forEach((b) => {
          b.classList.toggle("on-accept", state.verdicts[evId] === "accept" && b.dataset.verdict === "accept");
          b.classList.toggle("on-reject", state.verdicts[evId] === "reject" && b.dataset.verdict === "reject");
        });
      });
    });
  });

  document.querySelectorAll(".decide button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".decide button").forEach((b) => (b.disabled = true));
      await api("/api/cases/" + id + "/decision", {
        method: "POST",
        body: JSON.stringify({
          action: btn.dataset.action,
          risk_override: $("#riskOverride").value || null,
          indicator_verdicts: state.verdicts,
          rationale: $("#rationale").value.trim() || null,
        }),
      });
      await openCase(id);
      await loadQueue();
    });
  });

  const addNote = async () => {
    const input = $("#noteInput");
    if (!input.value.trim()) return;
    await api("/api/cases/" + id + "/notes", { method: "POST", body: JSON.stringify({ body: input.value.trim() }) });
    await openCase(id);
    await loadQueue();
  };
  $("#addNoteBtn").addEventListener("click", addNote);
  $("#noteInput").addEventListener("keydown", (e) => e.key === "Enter" && addNote());

  $("#chatSendBtn").addEventListener("click", () => sendChat($("#chatInput").value));
  $("#chatInput").addEventListener("keydown", (e) => e.key === "Enter" && sendChat($("#chatInput").value));
  document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => sendChat(b.textContent)));
}

/* ---------------- streaming chat ---------------- */
async function sendChat(q) {
  q = (q || "").trim();
  if (!q) return;
  const id = state.detail.case_id;
  const log = $("#chatLog");
  $("#chatInput").value = "";
  $("#chatInput").disabled = $("#chatSendBtn").disabled = true;

  log.insertAdjacentHTML("beforeend", `<div class="msg investigator">${esc(q)}</div>`);
  const answerEl = document.createElement("div");
  answerEl.className = "msg assistant";
  answerEl.textContent = "…";
  log.appendChild(answerEl);
  log.scrollTop = log.scrollHeight;

  try {
    const res = await fetch(API + "/api/cases/" + id + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let answer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() || "";
      for (const f of frames) {
        const line = f.replace(/^data: /, "").trim();
        if (!line) continue;
        try {
          const p = JSON.parse(line);
          if (p.delta) {
            answer += p.delta;
            answerEl.innerHTML = md(answer);
            log.scrollTop = log.scrollHeight;
          }
        } catch {
          /* ignore keep-alives */
        }
      }
    }
    if (!answer) answerEl.textContent = "(no answer)";
  } catch (e) {
    answerEl.textContent = "Error: " + e.message;
  } finally {
    $("#chatInput").disabled = $("#chatSendBtn").disabled = false;
    $("#chatInput").focus();
  }
}

loadQueue();
