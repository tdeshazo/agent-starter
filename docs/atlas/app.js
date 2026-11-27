// Simple Agent — Interactive Codebase Atlas Engine
(function () {
  "use strict";

  const META = window.ATLAS_META || {};
  const EXCERPTS = window.ATLAS_EXCERPTS || {};
  const C4 = window.ATLAS_C4 || {};
  const INVENTORY = window.ATLAS_INVENTORY || [];
  const WALKTHROUGHS = window.ATLAS_WALKTHROUGHS || [];
  const TUTORIALS = window.ATLAS_TUTORIALS || [];
  const EXERCISES = window.ATLAS_EXERCISES || [];
  const QUIZZES = window.ATLAS_QUIZZES || [];

  const state = {
    view: "c4",
    c4Level: "l1",
    c4SelectedNode: null,
    wtId: WALKTHROUGHS[0] ? WALKTHROUGHS[0].id : null,
    wtStep: 0,
    tutStep: 0,
    tutExpr: "(12.5 + 7.5) * 3",
    lab: "turn",
    learningSub: "exercises",
    quizScore: {},
  };

  function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function badgeHtml(evidence) {
    if (evidence === "verified") return `<span class="badge badge-verified">VERIFIED RUNTIME</span>`;
    if (evidence === "static") return `<span class="badge badge-static">STATIC ANALYSIS</span>`;
    return `<span class="badge badge-assumption">EXTERNAL / ASSUMPTION</span>`;
  }

  function renderExcerpt(excerptId) {
    const ex = EXCERPTS[excerptId];
    if (!ex) return `<div class="muted">Excerpt not found: ${esc(excerptId)}</div>`;
    const lines = ex.code.split("\n");
    const rows = lines
      .map((line, i) => {
        const ln = ex.startLine + i;
        return `<div class="code-line"><span class="code-ln">${ln}</span><span>${esc(line)}</span></div>`;
      })
      .join("");
    return `
      <div class="code-block">
        <div class="code-header">
          <span><strong>${esc(ex.path)}</strong>:${ex.startLine}-${ex.endLine} · ${esc(ex.symbol)}</span>
          <span>Verbatim (${lines.length} lines)</span>
        </div>
        <div class="code-scroll">${rows}</div>
      </div>`;
  }

  // ---------- HEADER / THEME / TABS ----------
  function initMeta() {
    const banner = document.getElementById("meta-banner");
    const footer = document.getElementById("footer-meta");
    const tests = META.verifiedTests || { passed: 0, failed: 0 };
    if (banner) {
      banner.textContent = `Source snapshot ${META.short || "unknown"} (${META.branch || "main"}) · ${tests.passed}/${tests.passed + tests.failed} unit tests verified · generated ${META.generatedAt || ""}`;
    }
    if (footer) {
      footer.textContent = `Generated against Git commit ${META.commit || "unknown"} — "${META.subject || ""}"`;
    }
  }

  function switchView(viewId) {
    state.view = viewId;
    document.querySelectorAll(".view-section").forEach((el) => {
      el.classList.toggle("active", el.id === "view-" + viewId);
    });
    document.querySelectorAll(".main-tab").forEach((btn) => {
      const active = btn.dataset.view === viewId;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function initNav() {
    document.querySelectorAll(".main-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchView(btn.dataset.view));
    });
    const themeBtn = document.getElementById("btn-theme");
    themeBtn.addEventListener("click", () => {
      const root = document.documentElement;
      const isDark = root.getAttribute("data-theme") !== "light";
      root.setAttribute("data-theme", isDark ? "light" : "dark");
      themeBtn.textContent = isDark ? "☾ Dark" : "☀ Light";
      renderC4();
    });
  }

  // ---------- VIEW 1: C4 ARCHITECTURE ----------
  const KIND_COLORS = {
    person: { fill: "var(--c4-person-bg)", stroke: "var(--c4-person)" },
    system: { fill: "var(--c4-system-bg)", stroke: "var(--c4-system)" },
    container: { fill: "var(--c4-container-bg)", stroke: "var(--c4-container)" },
    component: { fill: "var(--c4-component-bg)", stroke: "var(--c4-component)" },
    external: { fill: "var(--c4-external-bg)", stroke: "var(--c4-external)" },
  };

  function wrapSvgText(text, maxChars) {
    const words = text.split(/\s+/);
    const lines = [];
    let cur = "";
    for (const w of words) {
      if ((cur + " " + w).trim().length <= maxChars) {
        cur = (cur + " " + w).trim();
      } else {
        if (cur) lines.push(cur);
        cur = w;
      }
    }
    if (cur) lines.push(cur);
    return lines.slice(0, 3);
  }

  function renderC4() {
    const level = C4[state.c4Level];
    if (!level) return;
    document.getElementById("c4-diagram-title").textContent = level.title;
    document.getElementById("c4-diagram-hint").textContent = level.subtitle;

    const maxX = Math.max(...level.nodes.map((n) => n.x + n.w)) + 40;
    const maxY = Math.max(...level.nodes.map((n) => n.y + n.h)) + 40;
    const byId = Object.fromEntries(level.nodes.map((n) => [n.id, n]));

    const edgesSvg = level.edges
      .map((e, idx) => {
        const a = byId[e.from];
        const b = byId[e.to];
        if (!a || !b) return "";
        const x1 = a.x + a.w / 2;
        const y1 = a.y + a.h / 2;
        const x2 = b.x + b.w / 2;
        const y2 = b.y + b.h / 2;
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const dash = e.evidence === "assumption" ? 'stroke-dasharray="5,4"' : "";
        return `
          <g>
            <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--border-bright)" stroke-width="1.6" ${dash} marker-end="url(#arrow)" />
            <circle cx="${mx}" cy="${my}" r="9" fill="var(--bg-elev)" stroke="var(--accent)" stroke-width="1.2" />
            <text x="${mx}" y="${my + 3.5}" text-anchor="middle" fill="var(--accent)" font-size="10" font-family="var(--mono)" font-weight="700">${idx + 1}</text>
          </g>`;
      })
      .join("");

    const nodesSvg = level.nodes
      .map((n) => {
        const c = KIND_COLORS[n.kind] || KIND_COLORS.component;
        const sel = state.c4SelectedNode === n.id ? "selected" : "";
        const titleLines = wrapSvgText(n.label, Math.floor(n.w / 9));
        const techLines = wrapSvgText(n.tech, Math.floor(n.w / 7.5));
        const titleTspans = titleLines
          .map((l, i) => `<tspan x="${n.x + 12}" dy="${i === 0 ? 0 : 16}">${esc(l)}</tspan>`)
          .join("");
        const techTspans = techLines
          .map((l, i) => `<tspan x="${n.x + 12}" dy="${i === 0 ? 0 : 13}">${esc(l)}</tspan>`)
          .join("");
        const evDot = n.evidence === "verified" ? "var(--ok)" : n.evidence === "static" ? "var(--accent)" : "var(--warn)";
        return `
          <g class="c4-node ${sel}" data-node="${esc(n.id)}">
            <rect class="node-box" x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="10" fill="${c.fill}" stroke="${c.stroke}" stroke-width="1.8" />
            <circle cx="${n.x + n.w - 12}" cy="${n.y + 13}" r="4.5" fill="${evDot}" />
            <text x="${n.x + 12}" y="${n.y + 24}" fill="var(--text)" font-size="13" font-weight="700">${titleTspans}</text>
            <text x="${n.x + 12}" y="${n.y + 24 + titleLines.length * 16 + 4}" fill="var(--text-dim)" font-size="10.5" font-family="var(--mono)">${techTspans}</text>
          </g>`;
      })
      .join("");

    document.getElementById("c4-svg-host").innerHTML = `
      <svg viewBox="0 0 ${maxX} ${maxY}" role="img" aria-label="${esc(level.title)}">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--border-bright)" />
          </marker>
        </defs>
        ${edgesSvg}
        ${nodesSvg}
      </svg>`;

    document.getElementById("c4-edge-list").innerHTML = level.edges
      .map((e, i) => {
        const a = byId[e.from];
        const b = byId[e.to];
        return `<div class="edge-chip"><strong>#${i + 1} ${esc(a ? a.label : e.from)} → ${esc(b ? b.label : e.to)}</strong><div>${esc(e.label)} ${badgeHtml(e.evidence)}</div></div>`;
      })
      .join("");

    document.querySelectorAll(".c4-node").forEach((el) => {
      el.addEventListener("click", () => {
        state.c4SelectedNode = el.dataset.node;
        renderC4();
        renderInspector(byId[el.dataset.node]);
      });
    });

    if (!state.c4SelectedNode || !byId[state.c4SelectedNode]) {
      state.c4SelectedNode = level.nodes[0].id;
    }
    renderInspector(byId[state.c4SelectedNode]);
  }

  function renderInspector(node) {
    const host = document.getElementById("c4-inspector");
    if (!node) return;
    const filesHtml = (node.files || []).map((f) => `<span class="file-ref">${esc(f)}</span>`).join(" ");
    const testsHtml = (node.tests || []).map((t) => `<li><code>${esc(t)}</code></li>`).join("");
    const excerptsHtml = (node.excerpts || []).map(renderExcerpt).join("");
    host.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
        <h3 style="margin:0;">${esc(node.label)}</h3>
        ${badgeHtml(node.evidence)}
      </div>
      <div class="muted" style="font-family:var(--mono);margin-bottom:10px;">${esc(node.tech)}</div>
      <p>${esc(node.summary)}</p>
      <h4>Source Locations</h4>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">${filesHtml}</div>
      <h4>Relevant Tests</h4>
      <ul style="margin:4px 0 12px 18px;padding:0;font-size:12px;">${testsHtml}</ul>
      <h4>Verbatim Source Excerpts</h4>
      ${excerptsHtml}
    `;
  }

  function initC4() {
    document.querySelectorAll("#c4-level-bar .pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.c4Level = btn.dataset.level;
        state.c4SelectedNode = null;
        document.querySelectorAll("#c4-level-bar .pill").forEach((b) => b.classList.toggle("active", b === btn));
        renderC4();
      });
    });
    renderC4();
  }

  // ---------- VIEW 2: SEARCHABLE FEATURE INVENTORY ----------
  function renderInventory() {
    const q = (document.getElementById("inv-search").value || "").trim().toLowerCase();
    const cat = document.getElementById("inv-category").value;
    const ev = document.getElementById("inv-evidence").value;

    const filtered = INVENTORY.filter((item) => {
      if (cat !== "all" && item.category !== cat) return false;
      if (ev !== "all" && item.evidence !== ev) return false;
      if (!q) return true;
      const hay = [item.title, item.summary, item.entry, ...(item.symbols || []), ...(item.tests || [])]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });

    document.getElementById("inv-count").textContent = `Showing ${filtered.length} of ${INVENTORY.length} features`;
    document.getElementById("inv-grid").innerHTML = filtered
      .map(
        (item) => `
      <article class="inv-card">
        <div class="inv-meta">
          ${item.priority ? `<span class="badge badge-priority">CORE PRIORITY</span>` : `<span class="badge badge-tag">${esc(item.category.toUpperCase())}</span>`}
          ${badgeHtml(item.evidence)}
        </div>
        <h3 style="margin:0;">${esc(item.title)}</h3>
        <div class="inv-meta">
          <span class="file-ref">${esc(item.entry)}</span>
          ${item.symbols.map((s) => `<span class="badge badge-tag">${esc(s)}</span>`).join("")}
        </div>
        <p style="margin:0;color:var(--text-dim);font-size:13px;">${esc(item.summary)}</p>
        <div class="muted" style="font-size:11.5px;">Tests: ${item.tests.map((t) => `<code>${esc(t)}</code>`).join(", ")}</div>
        <div style="margin-top:auto;padding-top:6px;">
          <button class="btn btn-sm" data-jump-wt="${esc(item.walkthrough)}">Open Walkthrough →</button>
        </div>
      </article>`
      )
      .join("");

    document.querySelectorAll("[data-jump-wt]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.wtId = btn.dataset.jumpWt;
        state.wtStep = 0;
        switchView("walkthroughs");
        renderWalkthroughs();
      });
    });
  }

  function initInventory() {
    ["inv-search", "inv-category", "inv-evidence"].forEach((id) => {
      document.getElementById(id).addEventListener("input", renderInventory);
      document.getElementById(id).addEventListener("change", renderInventory);
    });
    renderInventory();
  }

  // ---------- VIEW 3: WALKTHROUGHS ----------
  function renderSequenceSvg(seq) {
    const colW = 148;
    const padX = 24;
    const width = padX * 2 + seq.actors.length * colW;
    const topY = 18;
    const headerH = 34;
    const rowH = 38;
    const height = topY + headerH + seq.messages.length * rowH + 28;

    const actorXs = seq.actors.map((_, i) => padX + i * colW + colW / 2);

    const actorsSvg = seq.actors
      .map((name, i) => {
        const x = actorXs[i];
        return `
          <g>
            <line x1="${x}" y1="${topY + headerH}" x2="${x}" y2="${height - 14}" stroke="var(--border)" stroke-dasharray="4,4" />
            <rect x="${x - 62}" y="${topY}" width="124" height="${headerH}" rx="7" fill="var(--bg-elev)" stroke="var(--border-bright)" />
            <text x="${x}" y="${topY + 21}" text-anchor="middle" fill="var(--text)" font-size="11.5" font-weight="700">${esc(name)}</text>
          </g>`;
      })
      .join("");

    const msgsSvg = seq.messages
      .map((m, idx) => {
        const y = topY + headerH + 24 + idx * rowH;
        const x1 = actorXs[m.from];
        const x2 = actorXs[m.to];
        const stroke = m.evidence === "assumption" ? "var(--warn)" : "var(--accent)";
        const dash = m.evidence === "assumption" ? 'stroke-dasharray="5,3"' : "";
        if (m.from === m.to) {
          return `
            <g>
              <path d="M ${x1} ${y - 6} H ${x1 + 36} V ${y + 10} H ${x1 + 4}" fill="none" stroke="${stroke}" stroke-width="1.6" ${dash} marker-end="url(#seq-arrow)" />
              <text x="${x1 + 42}" y="${y + 4}" fill="var(--text-dim)" font-size="11" font-family="var(--mono)">${idx + 1}. ${esc(m.label)}</text>
            </g>`;
        }
        const midX = (x1 + x2) / 2;
        return `
          <g>
            <line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${stroke}" stroke-width="1.6" ${dash} marker-end="url(#seq-arrow)" />
            <text x="${midX}" y="${y - 6}" text-anchor="middle" fill="var(--text)" font-size="11" font-family="var(--mono)">${idx + 1}. ${esc(m.label)}</text>
          </g>`;
      })
      .join("");

    return `
      <div class="svg-host" style="padding:4px 0;">
        <svg viewBox="0 0 ${width} ${height}">
          <defs>
            <marker id="seq-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--accent)" />
            </marker>
          </defs>
          ${actorsSvg}
          ${msgsSvg}
        </svg>
      </div>`;
  }

  function renderWalkthroughs() {
    const sidebar = document.getElementById("wt-sidebar");
    const main = document.getElementById("wt-main");
    const wt = WALKTHROUGHS.find((w) => w.id === state.wtId) || WALKTHROUGHS[0];
    if (!wt) return;
    if (state.wtStep >= wt.steps.length) state.wtStep = 0;

    sidebar.innerHTML = WALKTHROUGHS.map(
      (item) => `
      <button class="wt-nav-btn ${item.id === wt.id ? "active" : ""}" data-wt="${esc(item.id)}">
        <div style="margin-bottom:4px;"><span class="badge ${item.priority.startsWith("CORE") ? "badge-priority" : "badge-tag"}">${esc(item.priority)}</span></div>
        <div class="wt-nav-title">${esc(item.title)}</div>
        <div class="wt-nav-sub">${esc(item.steps.length)} steps · ${esc(item.failures.length)} failure modes</div>
      </button>`
    ).join("");

    sidebar.querySelectorAll("[data-wt]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.wtId = btn.dataset.wt;
        state.wtStep = 0;
        renderWalkthroughs();
      });
    });

    const step = wt.steps[state.wtStep];
    const stepPills = wt.steps
      .map((s, i) => `<button class="step-pill ${i === state.wtStep ? "active" : ""}" data-step="${i}">Step ${i + 1}</button>`)
      .join("");

    const dataFlowHtml = wt.dataFlow
      .map((d, i) => `<span class="state-box">${esc(d)}</span>${i < wt.dataFlow.length - 1 ? '<span class="state-arrow">→</span>' : ""}`)
      .join("");
    const stateHtml = wt.stateTransitions
      .map((s, i) => `<span class="state-box">${esc(s)}</span>${i < wt.stateTransitions.length - 1 ? '<span class="state-arrow">⇒</span>' : ""}`)
      .join("");

    main.innerHTML = `
      <div class="wt-card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <h3 style="font-size:17px;margin:0;">${esc(wt.title)}</h3>
          ${badgeHtml(wt.evidence)}
        </div>
        <p class="muted" style="margin-top:4px;">${esc(wt.subtitle)}</p>
        <h4>Data Flow</h4>
        <div class="state-strip">${dataFlowHtml}</div>
        <h4>State Transitions</h4>
        <div class="state-strip">${stateHtml}</div>
        <h4>Sequence Diagram</h4>
        ${renderSequenceSvg(wt.sequence)}
      </div>

      <div class="wt-card">
        <div class="step-controls">
          <button class="btn btn-sm" id="wt-prev" ${state.wtStep === 0 ? "disabled" : ""}>← Prev</button>
          ${stepPills}
          <button class="btn btn-sm" id="wt-next" ${state.wtStep === wt.steps.length - 1 ? "disabled" : ""}>Next →</button>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
          <h3 style="margin:0;">${esc(step.title)}</h3>
          ${badgeHtml(step.evidence)}
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
          ${step.callChain.map((c) => `<span class="file-ref">${esc(c)}</span>`).join("")}
        </div>
        <p>${esc(step.explanation)}</p>
        ${renderExcerpt(step.excerptId)}
      </div>

      <div class="two-col">
        <div class="wt-card">
          <h3>Suggested Debugger Breakpoints</h3>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${wt.breakpoints
              .map(
                (bp) => `
              <div class="bp-item">
                <div><span class="file-ref">${esc(bp.loc)}</span></div>
                <div class="muted" style="margin-top:4px;"><strong>Watch:</strong> <code>${esc(bp.watch)}</code></div>
                <div style="font-size:12.5px;margin-top:3px;">${esc(bp.why)}</div>
              </div>`
              )
              .join("")}
          </div>
        </div>
        <div class="wt-card">
          <h3>Failure Scenarios &amp; Recovery</h3>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${wt.failures
              .map(
                (f) => `
              <div class="fail-item">
                <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;">
                  <strong>${esc(f.title)}</strong>
                  ${badgeHtml(f.evidence)}
                </div>
                <div class="muted" style="margin-top:3px;"><strong>Symptom:</strong> ${esc(f.symptom)}</div>
                <div style="font-size:12.5px;margin-top:3px;"><strong>Handling:</strong> ${esc(f.handling)}</div>
              </div>`
              )
              .join("")}
          </div>
        </div>
      </div>

      <div class="wt-card">
        <h3>Verified Test Coverage</h3>
        <ul style="margin:6px 0 0 18px;padding:0;font-size:12.5px;">
          ${wt.tests.map((t) => `<li><code>${esc(t)}</code></li>`).join("")}
        </ul>
      </div>
    `;

    main.querySelectorAll("[data-step]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.wtStep = Number(btn.dataset.step);
        renderWalkthroughs();
      });
    });
    const prev = document.getElementById("wt-prev");
    const next = document.getElementById("wt-next");
    if (prev) prev.addEventListener("click", () => { state.wtStep = Math.max(0, state.wtStep - 1); renderWalkthroughs(); });
    if (next) next.addEventListener("click", () => { state.wtStep = Math.min(wt.steps.length - 1, state.wtStep + 1); renderWalkthroughs(); });
  }

  // ---------- VIEW 3B: TUTORIAL — ADD A NEW TOOL ----------
  function evaluateSafeCalcSim(expr) {
    const trace = [];
    if (!expr || !expr.trim()) {
      return { ok: false, error: "ValueError: Expression must be nonblank.", trace: ["Gate 1 (Nonblank): BLOCKED"] };
    }
    if (expr.length > 256) {
      return { ok: false, error: "ValueError: Expression exceeds the 256-character limit.", trace: ["Gate 1 (Length <= 256): BLOCKED"] };
    }
    trace.push(`Gate 1 (Length ${expr.length} <= 256): PASS`);

    if (/\b(True|False)\b/.test(expr)) {
      return { ok: false, error: "ValueError: Unsupported expression element: Constant (bool rejected).", trace: [...trace, "Gate 2 (AST Whitelist): BLOCKED — bool is rejected"] };
    }
    if (/['"]/.test(expr)) {
      return { ok: false, error: "ValueError: Unsupported expression element: Constant (str rejected).", trace: [...trace, "Gate 2 (AST Whitelist): BLOCKED — string literal rejected"] };
    }
    if (/[A-Za-z_]/.test(expr)) {
      const bad = expr.match(/[A-Za-z_][A-Za-z0-9_]*/)[0];
      return { ok: false, error: `ValueError: Unsupported expression element: Name/Call ('${bad}' blocked — no eval()!).`, trace: [...trace, `Gate 2 (AST Whitelist): BLOCKED — identifier '${bad}' is not in {Expression, BinOp, UnaryOp, numeric Constant}`] };
    }

    // Tokenize safe arithmetic expression
    const tokens = [];
    let i = 0;
    while (i < expr.length) {
      const ch = expr[i];
      if (/\s/.test(ch)) { i++; continue; }
      if (expr.startsWith("**", i) || expr.startsWith("//", i)) {
        tokens.push({ t: "op", v: expr.slice(i, i + 2) }); i += 2; continue;
      }
      if ("+-*/%()".includes(ch)) {
        tokens.push({ t: ch === "(" || ch === ")" ? ch : "op", v: ch }); i++; continue;
      }
      const numMatch = expr.slice(i).match(/^(?:\d+(?:\.\d*)?|\.\d+)/);
      if (numMatch) {
        tokens.push({ t: "num", v: Number(numMatch[0]) }); i += numMatch[0].length; continue;
      }
      return { ok: false, error: `ValueError: Invalid arithmetic syntax near '${ch}'.`, trace: [...trace, `Gate 2 (Tokenizer): BLOCKED unexpected char '${ch}'`] };
    }

    let pos = 0;
    let nodes = 0;
    const tick = () => {
      nodes += 1;
      if (nodes > 64) throw new Error("ValueError: Expression is too complex.");
    };
    const peek = () => tokens[pos];
    const eat = () => tokens[pos++];

    function parseExpr() {
      let left = parseTerm();
      while (peek() && peek().t === "op" && (peek().v === "+" || peek().v === "-")) {
        const op = eat().v;
        const right = parseTerm();
        tick();
        left = op === "+" ? left + right : left - right;
      }
      return left;
    }
    function parseTerm() {
      let left = parseUnary();
      while (peek() && peek().t === "op" && ["*", "/", "//", "%"].includes(peek().v)) {
        const op = eat().v;
        const right = parseUnary();
        tick();
        if ((op === "/" || op === "//" || op === "%") && right === 0) {
          throw new Error("ValueError: Division by zero.");
        }
        if (op === "*") left = left * right;
        else if (op === "/") left = left / right;
        else if (op === "//") left = Math.floor(left / right);
        else left = ((left % right) + right) % right;
      }
      return left;
    }
    function parseUnary() {
      if (peek() && peek().t === "op" && (peek().v === "+" || peek().v === "-")) {
        const op = eat().v;
        tick();
        const val = parseUnary();
        return op === "-" ? -val : +val;
      }
      return parsePower();
    }
    function parsePower() {
      let base = parsePrimary();
      if (peek() && peek().t === "op" && peek().v === "**") {
        eat();
        const exp = parseUnary();
        tick();
        if (Math.abs(exp) > 1000 || Math.abs(base) > 10_000_000) {
          throw new Error("ValueError: Exponent or base exceeds calculator limits.");
        }
        base = Math.pow(base, exp);
      }
      return base;
    }
    function parsePrimary() {
      const tok = peek();
      if (!tok) throw new Error("ValueError: Invalid arithmetic syntax.");
      if (tok.t === "num") { eat(); tick(); return tok.v; }
      if (tok.t === "(") {
        eat();
        const val = parseExpr();
        if (!peek() || peek().t !== ")") throw new Error("ValueError: Invalid arithmetic syntax (missing ')').");
        eat();
        return val;
      }
      throw new Error("ValueError: Invalid arithmetic syntax.");
    }

    try {
      const result = parseExpr();
      if (pos !== tokens.length) throw new Error("ValueError: Invalid arithmetic syntax.");
      if (!Number.isFinite(result)) throw new Error("ValueError: Result is not a finite real number.");
      trace.push(`Gate 2 (AST Whitelist & Node Budget): PASS (${nodes} / 64 AST nodes)`);
      trace.push("Gate 3 (Exponent, Div-by-Zero & Finite Guards): PASS");
      return { ok: true, value: String(result), trace };
    } catch (err) {
      return { ok: false, error: err.message, trace: [...trace, `Gate 3 (Safety Guard): BLOCKED — ${err.message}`] };
    }
  }

  function renderTutorial() {
    const tut = TUTORIALS[0];
    const host = document.getElementById("tutorial-stage");
    if (!tut || !host) return;
    const step = tut.steps[state.tutStep];
    const sim = evaluateSafeCalcSim(state.tutExpr);
    const presets = [
      "(12.5 + 7.5) * 3",
      "-5 + 2 ** 3",
      "17 // 5",
      "1 / 0",
      "2 ** 1001",
      "True + 1",
      "__import__('os').system('id')",
    ];

    host.innerHTML = `
      <div class="wt-card" style="margin-bottom:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
          <h3 style="font-size:17px;margin:0;">${esc(tut.title)}</h3>
          <span class="badge badge-assumption">${esc(tut.badge)}</span>
        </div>
        <p class="muted">${esc(tut.subtitle)}</p>
        <h4>Repository Touchpoints</h4>
        <table class="data-table">
          <thead><tr><th>File</th><th>Action</th><th>Why</th></tr></thead>
          <tbody>
            ${tut.touchpoints
              .map(
                (tp) => `
              <tr>
                <td><span class="file-ref">${esc(tp.file)}</span></td>
                <td><span class="badge ${tp.change === "Edit" ? "badge-priority" : "badge-verified"}">${esc(tp.change)}</span></td>
                <td>${esc(tp.role)}</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>

      <div class="wt-card" style="margin-bottom:14px;">
        <div class="step-controls">
          <button class="btn btn-sm" id="tut-prev" ${state.tutStep === 0 ? "disabled" : ""}>← Prev</button>
          ${tut.steps.map((_, i) => `<button class="step-pill ${i === state.tutStep ? "active" : ""}" data-tut-step="${i}">Step ${i + 1}</button>`).join("")}
          <button class="btn btn-sm" id="tut-next" ${state.tutStep === tut.steps.length - 1 ? "disabled" : ""}>Next →</button>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
          <h3 style="margin:0;">${esc(step.title)}</h3>
          ${badgeHtml(step.evidence)}
        </div>
        <p>${esc(step.summary)}</p>
        <h4>Actionable Checklist</h4>
        <ul style="margin:4px 0 12px 18px;padding:0;font-size:13px;">
          ${step.checklist.map((item) => `<li>${esc(item)}</li>`).join("")}
        </ul>
        <h4>Existing Codebase Reference (Verbatim)</h4>
        ${renderExcerpt(step.excerptId)}
      </div>

      <div class="wt-card" style="margin-bottom:14px;">
        <h3>Interactive Sandbox — Test the Safe Calculator AST &amp; DoS Guards</h3>
        <p class="muted">Try valid arithmetic and hostile LLM inputs to see how the AST whitelist and resource limits protect the process (no <code>eval()</code>).</p>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
          ${presets.map((p) => `<button class="btn btn-sm" data-tut-preset="${esc(p)}"><code>${esc(p)}</code></button>`).join("")}
        </div>
        <div class="filter-bar">
          <input id="tut-expr-input" class="search-input" value="${esc(state.tutExpr)}" placeholder="Enter arithmetic expression…">
          <button class="btn btn-primary" id="tut-expr-run">Evaluate</button>
        </div>
        <div class="bp-item" style="border-left-color:${sim.ok ? "var(--ok)" : "var(--err)"};margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong>${sim.ok ? `Result: ${esc(sim.value)}` : esc(sim.error)}</strong>
            <span class="badge ${sim.ok ? "badge-verified" : "badge-assumption"}" style="${sim.ok ? "" : "background:var(--err-bg);color:var(--err);border-color:rgba(239,68,68,.35);"}">${sim.ok ? "SAFE RETURN" : "BLOCKED"}</span>
          </div>
          <div class="muted" style="margin-top:6px;font-family:var(--mono);font-size:12px;">${sim.trace.map(esc).join("<br>")}</div>
        </div>
      </div>

      <div class="wt-card">
        <h3>Reference Implementation (Hidden by Default)</h3>
        <p class="muted">Try implementing <code>calculate</code> yourself first using the 6 steps above, then expand to compare against a <code>ruff</code>-clean reference.</p>
        <details class="disclosure">
          <summary>1. Reference <code>calculate</code> tool for <code>simple_agent/tools/calculator.py</code></summary>
          <div class="disclosure-body"><pre class="term-sim" style="min-height:auto;margin:0;">${esc(tut.referenceCode.toolsPy)}</pre></div>
        </details>
        <details class="disclosure">
          <summary>2. Reference <code>SYSTEM_PROMPT</code> update for <code>simple_agent/prompts.py</code></summary>
          <div class="disclosure-body"><pre class="term-sim" style="min-height:auto;margin:0;">${esc(tut.referenceCode.promptsPy)}</pre></div>
        </details>
        <details class="disclosure">
          <summary>3. Reference unit tests for <code>tests/test_tools.py</code></summary>
          <div class="disclosure-body"><pre class="term-sim" style="min-height:auto;margin:0;">${esc(tut.referenceCode.testsPy)}</pre></div>
        </details>
      </div>
    `;

    host.querySelectorAll("[data-tut-step]").forEach((btn) => {
      btn.onclick = () => { state.tutStep = Number(btn.dataset.tutStep); renderTutorial(); };
    });
    document.getElementById("tut-prev").onclick = () => { state.tutStep = Math.max(0, state.tutStep - 1); renderTutorial(); };
    document.getElementById("tut-next").onclick = () => { state.tutStep = Math.min(tut.steps.length - 1, state.tutStep + 1); renderTutorial(); };
    host.querySelectorAll("[data-tut-preset]").forEach((btn) => {
      btn.onclick = () => { state.tutExpr = btn.dataset.tutPreset; renderTutorial(); };
    });
    const runExpr = () => {
      state.tutExpr = document.getElementById("tut-expr-input").value;
      renderTutorial();
    };
    document.getElementById("tut-expr-run").onclick = runExpr;
    document.getElementById("tut-expr-input").onkeydown = (e) => { if (e.key === "Enter") runExpr(); };
  }

  // ---------- VIEW 4: INTERACTIVE LABS ----------
  // Lab 1: Turn Lifecycle & conversation_turn Rollback Simulator
  const turnSteps = [
    {
      label: "0. Idle (Prior Turn Committed)",
      messages: ["[0] user: 'What is max_tokens?'", "[1] assistant: 'Let me check.'"],
      committed: ["╭─ Simple Agent (v0.1.0) ─────────────────────────╮", "│ model: gemma-4-e4b · endpoint: 127.0.0.1:8088/v1 │", "╰──────────────────────────────────────────────────╯"],
      tail: [],
      pendingTools: {},
      running: false,
      note: "Clean baseline before `AgentTui.submit()`. `history = agent.messages.copy()` will capture indices [0..1]."
    },
    {
      label: "1. Submit Prompt & Snapshot History",
      messages: ["[0] user: 'What is max_tokens?'", "[1] assistant: 'Let me check.'", "[2] user: 'Find max_tokens in simple_agent/agent.py'"],
      committed: ["[header]", "", "› Find max_tokens in simple_agent/agent.py"],
      tail: [],
      pendingTools: {},
      running: true,
      note: "`conversation_turn(agent.messages)` snapshotted 2 messages. `_respond()` and `_animate()` background tasks are running."
    },
    {
      label: "2. Model Emits toolUse(search_text)",
      messages: ["[0..1] (prior)", "[2] user: 'Find max_tokens...'", "[3] assistant: toolUse(id=c1, name='search_text', query='max_tokens')"],
      committed: ["[header]", "", "› Find max_tokens in simple_agent/agent.py"],
      tail: ["• Calling search_text({\"query\": \"max_tokens\"})"],
      pendingTools: { c1: "search_text" },
      running: true,
      note: "Notice `Calling search_text(...)` lives ONLY in `Transcript.tail()`, not committed `_history.rows`! Try clicking 'Trigger Esc Interrupt' now."
    },
    {
      label: "3. toolResult Committed & Streaming Reply",
      messages: ["[0..1] (prior)", "[2] user: 'Find max_tokens...'", "[3] assistant: toolUse(c1)", "[4] user: toolResult(c1, 'simple_agent/agent.py:33: ...')"],
      committed: ["[header]", "", "› Find max_tokens in simple_agent/agent.py", "", "• Called search_text({\"query\": \"max_tokens\"})", "  └ simple_agent/agent.py:33: \"max_tokens\": 2048,"],
      tail: ["• max_tokens is set to 2048 in simple_agent/"],
      pendingTools: {},
      running: true,
      note: "`c1` popped from `pending_tools` and committed with `└` preview. Partial response text streams in `StreamCell.tail()`."
    },
    {
      label: "4. Turn Complete (end_turn)",
      messages: ["[0..1] (prior)", "[2] user", "[3] assistant: toolUse(c1)", "[4] user: toolResult(c1)", "[5] assistant: 'max_tokens is set to 2048 in simple_agent/agent.py:33.'"],
      committed: ["[header]", "", "› Find max_tokens in simple_agent/agent.py", "", "• Called search_text({\"query\": \"max_tokens\"})", "  └ simple_agent/agent.py:33: \"max_tokens\": 2048,", "", "• max_tokens is set to 2048 in simple_agent/agent.py:33.", "", "─ Worked for 2s ─────────────────────────", "  in 412 · cached 280 · out 29"],
      tail: [],
      pendingTools: {},
      running: false,
      note: "`conversation_turn` exited normally (all 6 messages retained). `end_turn()` flushed StreamCell, emitted separator & usage cell."
    }
  ];
  let lab1Idx = 0;
  let lab1Outcome = null; // null | "esc" | "err"

  function renderLabTurn(host) {
    const s = turnSteps[lab1Idx];
    let msgs = s.messages;
    let committed = [...s.committed];
    let tail = [...s.tail];
    let pending = Object.keys(s.pendingTools);
    let note = s.note;

    if (lab1Outcome === "esc") {
      msgs = turnSteps[0].messages;
      committed.push("", "■ Response stopped — tell the agent what to do differently.");
      tail = [];
      pending = [];
      note = "ESC PRESSED! `interrupt()` set `stop_requested=True` and cancelled `self.task`. `CancelledError` (a BaseException) triggered `messages[:] = history`, rolling `agent.messages` cleanly back to [0..1]!";
    } else if (lab1Outcome === "err") {
      msgs = turnSteps[0].messages;
      committed.push("", "■ APIConnectionError: Could not connect to model server");
      tail = [];
      pending = [];
      note = "NETWORK ERROR! `conversation_turn` rolled `agent.messages` back to [0..1] and `format_invocation_error()` rendered a safe error cell without crashing the TUI.";
    }

    host.innerHTML = `
      <h3>Lab 1 — Turn Lifecycle &amp; <code>conversation_turn</code> Rollback Simulator</h3>
      <p class="muted">Step through a live multi-tool turn and trigger an interruption or error at any mid-turn state to observe how <code>agent.messages</code>, <code>pending_tools</code>, committed <code>rows</code>, and ephemeral <code>tail()</code> behave.</p>
      <div class="step-controls">
        <button class="btn btn-sm" id="l1-prev" ${lab1Idx === 0 && !lab1Outcome ? "disabled" : ""}>← Prev</button>
        <button class="btn btn-sm btn-primary" id="l1-next" ${lab1Idx === turnSteps.length - 1 || lab1Outcome ? "disabled" : ""}>Next Step →</button>
        <button class="btn btn-sm btn-danger" id="l1-esc" ${!s.running || lab1Outcome ? "disabled" : ""}>Press Esc (Interrupt)</button>
        <button class="btn btn-sm btn-danger" id="l1-err" ${!s.running || lab1Outcome ? "disabled" : ""}>Inject APIConnectionError</button>
        <button class="btn btn-sm" id="l1-reset">Reset</button>
      </div>
      <div class="kv-grid">
        <div class="kv-box"><div class="kv-label">Phase</div><div class="kv-val">${esc(lab1Outcome ? (lab1Outcome === "esc" ? "ROLLED BACK (Esc)" : "ROLLED BACK (Error)") : s.label)}</div></div>
        <div class="kv-box"><div class="kv-label">agent.messages len</div><div class="kv-val">${msgs.length}</div></div>
        <div class="kv-box"><div class="kv-label">pending_tools</div><div class="kv-val">${pending.length ? pending.join(", ") : "(empty)"}</div></div>
        <div class="kv-box"><div class="kv-label">running</div><div class="kv-val">${(!lab1Outcome && s.running) ? "True" : "False"}</div></div>
      </div>
      <div class="two-col">
        <div>
          <h4>Simulated Terminal (Committed vs Live tail)</h4>
          <div class="term-sim"><div class="term-committed">${esc(committed.join("\n"))}</div>${tail.length ? `<div class="term-tail">${esc(tail.join("\n"))}</div>` : ""}</div>
        </div>
        <div>
          <h4>In-Memory <code>agent.messages</code></h4>
          <div class="term-sim">${esc(msgs.join("\n"))}</div>
        </div>
      </div>
      <p style="margin-top:10px;color:var(--accent);font-size:13px;"><strong>Architect Note:</strong> ${esc(note)}</p>
    `;

    document.getElementById("l1-prev").onclick = () => { if (lab1Outcome) { lab1Outcome = null; } else { lab1Idx = Math.max(0, lab1Idx - 1); } renderLabTurn(host); };
    document.getElementById("l1-next").onclick = () => { lab1Idx = Math.min(turnSteps.length - 1, lab1Idx + 1); renderLabTurn(host); };
    document.getElementById("l1-esc").onclick = () => { lab1Outcome = "esc"; renderLabTurn(host); };
    document.getElementById("l1-err").onclick = () => { lab1Outcome = "err"; renderLabTurn(host); };
    document.getElementById("l1-reset").onclick = () => { lab1Idx = 0; lab1Outcome = null; renderLabTurn(host); };
  }

  // Lab 2: Tool Security & Budget Inspector
  let lab2Path = "simple_agent/agent.py";
  let lab2Start = "22";
  let lab2End = "46";
  let lab2Kind = "regular"; // regular | symlink_outside | symlink_env | fifo | dir
  let lab2Size = 1800;

  let lab2SelectedBytes = null;

  function renderLabSecurity(host) {
    const trace = evaluateAtlasReadFile({
      path: lab2Path, start: lab2Start, end: lab2End, kind: lab2Kind,
      size: lab2Size, selectedBytes: lab2SelectedBytes,
    });
    const presets = [
      { label: "Absolute path inside workspace", path: "/workspace/simple_agent/agent.py", s: "22", e: "46", k: "regular", sz: 1800 },
      { label: "../secret.txt", path: "../secret.txt", s: "", e: "", k: "regular", sz: 120 },
      { label: ".env (blocked)", path: ".env", s: "", e: "", k: "regular", sz: 170 },
      { label: ".env.example (allowed)", path: ".env.example", s: "", e: "", k: "regular", sz: 170 },
      { label: "symlink -> .env", path: "env_link.txt", s: "", e: "", k: "symlink_env", sz: 170 },
      { label: "pipe.fifo (DoS)", path: "pipe.fifo", s: "", e: "", k: "fifo", sz: 0 },
      { label: "64 KiB whole-file (over 4 KiB)", path: "docs/large.txt", s: "", e: "", k: "regular", sz: 65536 },
      { label: "64 KiB ranged (<= 1 MiB)", path: "docs/large.txt", s: "1", e: "10", k: "regular", sz: 65536, selected: 2048 },
      { label: "Range over 4 KiB", path: "docs/large.txt", s: "1", e: "10", k: "regular", sz: 65536, selected: 4097 },
    ];

    host.innerHTML = `
      <h3>Lab 2 — <code>read_file</code> Security Gate &amp; <code>search_text</code> Budget Inspector</h3>
      <p class="muted">Simulate a read from <code>/workspace</code>. The selected byte count models the output from the requested line range.</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
        ${presets.map((p, i) => `<button class="btn btn-sm" data-l2p="${i}">${esc(p.label)}</button>`).join("")}
      </div>
      <div class="filter-bar">
        <input id="l2-path" class="search-input" style="flex:2 1 200px;" value="${esc(lab2Path)}" placeholder="path">
        <input id="l2-start" class="search-input" style="flex:0 1 95px;" value="${esc(lab2Start)}" placeholder="start_line">
        <input id="l2-end" class="search-input" style="flex:0 1 95px;" value="${esc(lab2End)}" placeholder="end_line">
        <select id="l2-kind" class="select-input">
          <option value="regular" ${lab2Kind === "regular" ? "selected" : ""}>Regular file</option>
          <option value="symlink_outside" ${lab2Kind === "symlink_outside" ? "selected" : ""}>Symlink -> outside root</option>
          <option value="symlink_env" ${lab2Kind === "symlink_env" ? "selected" : ""}>Symlink -> .env</option>
          <option value="fifo" ${lab2Kind === "fifo" ? "selected" : ""}>Named pipe (FIFO)</option>
          <option value="dir" ${lab2Kind === "dir" ? "selected" : ""}>Directory</option>
        </select>
        <input id="l2-size" type="number" class="search-input" style="flex:0 1 115px;" value="${lab2Size}" min="0" step="1" aria-label="File size in bytes">
        <input id="l2-selected" type="number" class="search-input" style="flex:0 1 150px;" min="0" step="1"
          value="${lab2SelectedBytes ?? ""}" placeholder="Range bytes" aria-label="Selected range size in bytes">
      </div>
      <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">
        ${trace
          .map(
            (t) => `
          <div class="bp-item" style="border-left-color:${t.status === "pass" ? "var(--ok)" : t.status === "unknown" ? "var(--accent)" : "var(--err)"};">
            <div style="display:flex;justify-content:space-between;">
              <strong>${esc(t.gate)}</strong>
              <span class="badge ${t.status === "pass" ? "badge-verified" : "badge-assumption"}" style="${t.status === "fail" ? "background:var(--err-bg);color:var(--err);" : ""}">${t.status === "pass" ? "PASS" : t.status === "fail" ? "BLOCKED" : "NEEDS INPUT"}</span>
            </div>
            <div class="muted" style="margin-top:3px;">${esc(t.detail)}</div>
          </div>`
          )
          .join("")}
      </div>
      <h4><code>search_text</code> Resource Budgets (<code>tools/workspace_files.py</code> and <code>tools/workspace_text.py</code>)</h4>
      <div class="kv-grid">
        <div class="kv-box"><div class="kv-label">Max Matches</div><div class="kv-val">20 rows</div></div>
        <div class="kv-box"><div class="kv-label">Max Output</div><div class="kv-val">4,096 B (reserves notice)</div></div>
        <div class="kv-box"><div class="kv-label">Max Scanned Entries</div><div class="kv-val">10,000 entries</div></div>
        <div class="kv-box"><div class="kv-label">Max Total Read</div><div class="kv-val">32 MiB</div></div>
        <div class="kv-box"><div class="kv-label">Max File Size</div><div class="kv-val">1 MiB</div></div>
        <div class="kv-box"><div class="kv-label">Max Recursion Depth</div><div class="kv-val">32 levels</div></div>
      </div>
    `;

    host.querySelectorAll("[data-l2p]").forEach((btn) => {
      btn.onclick = () => {
        const p = presets[Number(btn.dataset.l2p)];
        lab2Path = p.path; lab2Start = p.s; lab2End = p.e; lab2Kind = p.k; lab2Size = p.sz; lab2SelectedBytes = p.selected ?? null;
        renderLabSecurity(host);
      };
    });
    const sync = () => {
      lab2Path = document.getElementById("l2-path").value;
      lab2Start = document.getElementById("l2-start").value;
      lab2End = document.getElementById("l2-end").value;
      lab2Kind = document.getElementById("l2-kind").value;
      lab2Size = Number(document.getElementById("l2-size").value) || 0;
      const selected = document.getElementById("l2-selected").value;
      lab2SelectedBytes = selected === "" ? null : Number(selected);
      renderLabSecurity(host);
    };
    ["l2-path", "l2-start", "l2-end", "l2-kind", "l2-size", "l2-selected"].forEach((id) => {
      document.getElementById(id).onchange = sync;
    });
  }

  // Lab 3: StreamCell Streaming Markdown & Split-ANSI Simulator
  const ANSI_RE = /\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[P^_][^\x1b]*\x1b\\|[@-Z\\-_])|\x9b[0-?]*[ -/]*[@-~]/g;
  const INCOMPLETE_ANSI_RE = /(?:\x1b(?:\[[0-?]*[ -/]*|\][^\x07\x1b]*|[P^_][^\x1b]*)?|\x9b[0-?]*[ -/]*)$/;

  let lab3State = {
    committed: [],
    line: "",
    pendingEscape: "",
    fence: null,
    tableLines: [],
  };

  function lab3Push(chunk) {
    let raw = lab3State.pendingEscape + chunk;
    lab3State.pendingEscape = "";
    const m = raw.match(INCOMPLETE_ANSI_RE);
    if (m && m[0].length <= 256) {
      lab3State.pendingEscape = m[0];
      raw = raw.slice(0, raw.length - m[0].length);
    }
    const cleaned = raw.replace(/\r\n/g, "\n").replace(ANSI_RE, "");
    const parts = (lab3State.line + cleaned).split("\n");
    lab3State.line = parts.pop();

    for (const line of parts) {
      const trimmed = line.trimStart();
      if (!lab3State.fence && (trimmed.startsWith("```") || trimmed.startsWith("~~~"))) {
        if (lab3State.tableLines.length) {
          lab3State.committed.push("[TABLE FLUSHED] " + lab3State.tableLines.join(" / "));
          lab3State.tableLines = [];
        }
        lab3State.fence = trimmed[0].repeat(3);
        lab3State.committed.push("  [FENCE OPEN] " + line);
        continue;
      }
      if (lab3State.fence && trimmed.startsWith(lab3State.fence)) {
        lab3State.fence = null;
        lab3State.committed.push("  [FENCE CLOSE] " + line);
        continue;
      }
      if (lab3State.fence) {
        lab3State.committed.push("  " + line);
        continue;
      }
      if (lab3State.tableLines.length === 1) {
        if (/^[ \t|:-]+$/.test(line) && line.includes("-")) {
          lab3State.tableLines.push(line);
          continue;
        }
        lab3State.committed.push("• " + lab3State.tableLines.pop());
      } else if (lab3State.tableLines.length >= 2) {
        if (line.includes("|")) {
          lab3State.tableLines.push(line);
          continue;
        }
        lab3State.committed.push("╭─ [TABLE " + lab3State.tableLines.length + " rows rendered] ─╮");
        lab3State.tableLines = [];
      }
      if (line.includes("|") && !trimmed.startsWith("#")) {
        lab3State.tableLines.push(line);
      } else if (line.trim()) {
        lab3State.committed.push((lab3State.committed.length === 0 ? "• " : "  ") + line);
      }
    }
    if (lab3State.tableLines.length === 1 && lab3State.line && !/^[ \t|:-]+$/.test(lab3State.line)) {
      lab3State.committed.push("• " + lab3State.tableLines.pop());
    }
  }

  function renderLabStream(host) {
    const tailPreview = [];
    if (lab3State.tableLines.length >= 2) {
      tailPreview.push(`[LIVE TABLE PREVIEW: ${lab3State.tableLines.length} lines buffered]`);
    } else if (lab3State.tableLines.length === 1) {
      tailPreview.push(`[TABLE CANDIDATE HELD]: ${lab3State.tableLines[0]}`);
    }
    if (lab3State.line) tailPreview.push(`  ${lab3State.line}`);

    const formatStyled = (str) =>
      esc(str).replace(/\*\*(.+?)\*\*/g, '<span class="term-bold-red">$1</span>');

    host.innerHTML = `
      <h3>Lab 3 — <code>StreamCell</code> Markdown, Table Lookahead &amp; Split-ANSI State Machine</h3>
      <p class="muted">Push chunks to see how <code>StreamCell.push()</code> buffers incomplete ANSI escapes, holds 1-line table candidates until line 2 disambiguates them, and renders bold Markdown in theme-aware red.</p>
      <div class="step-controls">
        <button class="btn btn-sm" id="l3-ansi1">Push Split ESC "\\x1b["</button>
        <button class="btn btn-sm" id="l3-ansi2">Push "31mHello **bold**\\n"</button>
        <button class="btn btn-sm" id="l3-tbl1">Push "| Key | Val |\\n"</button>
        <button class="btn btn-sm" id="l3-tbl2">Push "| --- | --- |\\n"</button>
        <button class="btn btn-sm" id="l3-tbl3">Push "| port | 8088 |\\n"</button>
        <button class="btn btn-sm" id="l3-notbl">Push "Not a table\\n"</button>
        <button class="btn btn-sm" id="l3-fence">Push "\`\`\`py\\nx=1\\n\`\`\`\\n"</button>
        <button class="btn btn-sm" id="l3-reset">Reset</button>
      </div>
      <div class="kv-grid">
        <div class="kv-box"><div class="kv-label">_pending_escape</div><div class="kv-val">${esc(JSON.stringify(lab3State.pendingEscape))}</div></div>
        <div class="kv-box"><div class="kv-label">_table_lines len</div><div class="kv-val">${lab3State.tableLines.length}</div></div>
        <div class="kv-box"><div class="kv-label">fence</div><div class="kv-val">${lab3State.fence ? esc(lab3State.fence) : "None"}</div></div>
        <div class="kv-box"><div class="kv-label">uncommitted line</div><div class="kv-val">${esc(JSON.stringify(lab3State.line))}</div></div>
      </div>
      <div class="term-sim"><div class="term-committed">${lab3State.committed.length ? lab3State.committed.map(formatStyled).join("\n") : '<span class="term-dim">(no committed rows yet)</span>'}</div>${tailPreview.length ? `<div class="term-tail">${tailPreview.map(formatStyled).join("\n")}</div>` : ""}</div>
    `;

    document.getElementById("l3-ansi1").onclick = () => { lab3Push("\x1b["); renderLabStream(host); };
    document.getElementById("l3-ansi2").onclick = () => { lab3Push("31mHello **bold**\n"); renderLabStream(host); };
    document.getElementById("l3-tbl1").onclick = () => { lab3Push("| Key | Val |\n"); renderLabStream(host); };
    document.getElementById("l3-tbl2").onclick = () => { lab3Push("| --- | --- |\n"); renderLabStream(host); };
    document.getElementById("l3-tbl3").onclick = () => { lab3Push("| port | 8088 |\n"); renderLabStream(host); };
    document.getElementById("l3-notbl").onclick = () => { lab3Push("Not a table\n"); renderLabStream(host); };
    document.getElementById("l3-fence").onclick = () => { lab3Push("```py\nx=1\n```\n"); renderLabStream(host); };
    document.getElementById("l3-reset").onclick = () => {
      lab3State = { committed: [], line: "", pendingEscape: "", fence: null, tableLines: [] };
      renderLabStream(host);
    };
  }

  // Lab 4: Sticky-Follow Scroll & Ctrl-T Pager
  let lab4 = {
    totalRows: 24,
    viewportH: 8,
    firstLine: null, // null = sticky bottom
    speed: 0.5,
    remainder: 0.0,
    inPager: false,
  };

  function lab4ScrollWheel(dir) {
    if ((dir < 0 && lab4.remainder > 0) || (dir > 0 && lab4.remainder < 0)) {
      lab4.remainder = 0.0;
    }
    const total = lab4.remainder + dir * 3 * lab4.speed;
    const lines = Math.trunc(total);
    lab4.remainder = total - lines;
    if (!lines) return;
    const maxFirst = Math.max(0, lab4.totalRows - lab4.viewportH);
    const curFirst = lab4.firstLine === null ? maxFirst : lab4.firstLine;
    if (lines < 0) {
      lab4.firstLine = Math.max(0, curFirst + lines);
    } else if (curFirst + lab4.viewportH - 1 + lines >= lab4.totalRows - 1) {
      lab4.firstLine = null;
      lab4.remainder = 0.0;
    } else {
      lab4.firstLine = Math.min(maxFirst, curFirst + lines);
    }
  }

  function renderLabScroll(host) {
    const maxFirst = Math.max(0, lab4.totalRows - lab4.viewportH);
    const viewTop = lab4.firstLine === null ? maxFirst : Math.min(lab4.firstLine, maxFirst);
    const visible = [];
    for (let r = viewTop; r < Math.min(lab4.totalRows, viewTop + lab4.viewportH); r++) {
      visible.push(`row ${String(r + 1).padStart(2, "0")} │ ${r === lab4.totalRows - 1 ? "Live tail token…" : "Committed transcript line #" + (r + 1)}`);
    }
    const footerStatus = !lab4.inPager && lab4.firstLine !== null ? "↑ scrolled" : "(auto-following bottom)";

    host.innerHTML = `
      <h3>Lab 4 — Sticky-Follow Scroll (<code>first_line</code>), Fractional Wheel &amp; <code>Ctrl-T</code> Pager</h3>
      <p class="muted">Models <code>AgentTui._scroll_wheel()</code> and <code>_scroll_lines()</code> (<code>simple_agent/tui/app.py:577-633</code>). Scroll up, then click "Stream +2 Live Rows" to verify the viewport stays pinned!</p>
      <div class="step-controls">
        <button class="btn btn-sm" id="l4-up">Wheel Up (-1)</button>
        <button class="btn btn-sm" id="l4-dn">Wheel Down (+1)</button>
        <button class="btn btn-sm btn-primary" id="l4-stream">Stream +2 Live Rows</button>
        <button class="btn btn-sm" id="l4-bot">Ctrl-End (Bottom)</button>
        <button class="btn btn-sm" id="l4-pager">Toggle Ctrl-T Pager (${lab4.inPager ? "ON" : "OFF"})</button>
        <label class="muted">mouse_scroll_speed:
          <select id="l4-speed" class="select-input" style="padding:4px 8px;">
            <option value="0.25" ${lab4.speed === 0.25 ? "selected" : ""}>0.25 (0.75 lines/tick)</option>
            <option value="0.5" ${lab4.speed === 0.5 ? "selected" : ""}>0.50 (1.5 lines/tick)</option>
            <option value="1" ${lab4.speed === 1 ? "selected" : ""}>1.0 (3 lines/tick)</option>
            <option value="2" ${lab4.speed === 2 ? "selected" : ""}>2.0 (6 lines/tick)</option>
          </select>
        </label>
      </div>
      <div class="kv-grid">
        <div class="kv-box"><div class="kv-label">_history.first_line</div><div class="kv-val">${lab4.firstLine === null ? "None (Live Follow)" : lab4.firstLine}</div></div>
        <div class="kv-box"><div class="kv-label">_scroll_remainder</div><div class="kv-val">${lab4.remainder.toFixed(2)}</div></div>
        <div class="kv-box"><div class="kv-label">Total Rows</div><div class="kv-val">${lab4.totalRows}</div></div>
        <div class="kv-box"><div class="kv-label">Footer Status</div><div class="kv-val">${esc(footerStatus)}</div></div>
      </div>
      <div class="term-sim">${lab4.inPager ? `<div class="term-tail">  T R A N S C R I P T     ${lab4.firstLine === null ? "Live" : "Row " + (lab4.firstLine + 1) + "/" + lab4.totalRows}</div>\n` : ""}${esc(visible.join("\n"))}</div>
    `;

    document.getElementById("l4-up").onclick = () => { lab4ScrollWheel(-1); renderLabScroll(host); };
    document.getElementById("l4-dn").onclick = () => { lab4ScrollWheel(1); renderLabScroll(host); };
    document.getElementById("l4-stream").onclick = () => { lab4.totalRows += 2; renderLabScroll(host); };
    document.getElementById("l4-bot").onclick = () => { lab4.firstLine = null; lab4.remainder = 0.0; renderLabScroll(host); };
    document.getElementById("l4-pager").onclick = () => { lab4.inPager = !lab4.inPager; renderLabScroll(host); };
    document.getElementById("l4-speed").onchange = (e) => { lab4.speed = Number(e.target.value); renderLabScroll(host); };
  }

  function renderLabs() {
    const host = document.getElementById("lab-stage");
    if (state.lab === "turn") renderLabTurn(host);
    else if (state.lab === "security") renderLabSecurity(host);
    else if (state.lab === "stream") renderLabStream(host);
    else renderLabScroll(host);
  }

  function initLabs() {
    document.querySelectorAll("#lab-selector .pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.lab = btn.dataset.lab;
        document.querySelectorAll("#lab-selector .pill").forEach((b) => b.classList.toggle("active", b === btn));
        renderLabs();
      });
    });
    renderLabs();
  }

  // ---------- VIEW 5: EXERCISES & COMPREHENSION QUIZZES ----------
  function renderLearning() {
    const host = document.getElementById("learning-stage");
    if (state.learningSub === "exercises") {
      host.innerHTML = EXERCISES.map(
        (ex) => `
        <article class="exercise-card">
          <div class="inv-meta" style="margin-bottom:6px;">
            <span class="badge badge-priority">${esc(ex.level)}</span>
            <span class="badge badge-tag">${esc(ex.subsystem)}</span>
          </div>
          <h3>${esc(ex.title)}</h3>
          <p class="muted">${esc(ex.goal)}</p>
          <div class="inv-meta" style="margin-bottom:10px;">
            ${ex.targets.map((t) => `<span class="file-ref">${esc(t)}</span>`).join("")}
          </div>
          <div class="term-sim" style="min-height:auto;margin-bottom:8px;">${esc(ex.task)}</div>
          <div class="muted">Verification command: <code>${esc(ex.verifyCmd)}</code></div>
          ${ex.hints
            .map(
              (h, idx) => `
            <details class="disclosure">
              <summary>Hint ${idx + 1}</summary>
              <div class="disclosure-body">${esc(h)}</div>
            </details>`
            )
            .join("")}
          <details class="disclosure">
            <summary>Reference Solution &amp; Reasoning (Hidden by default)</summary>
            <div class="disclosure-body">${esc(ex.solution)}</div>
          </details>
        </article>`
      ).join("");
    } else {
      const answered = Object.keys(state.quizScore).length;
      const gotIt = Object.values(state.quizScore).filter(Boolean).length;
      host.innerHTML = `
        <div class="wt-card" style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <div><strong>Self-Check Progress:</strong> ${gotIt} / ${QUIZZES.length} marked confident (${answered} reviewed)</div>
          <button class="btn btn-sm" id="quiz-reset">Reset Progress</button>
        </div>
        ${QUIZZES.map(
          (q, idx) => `
          <article class="quiz-card">
            <div class="inv-meta" style="margin-bottom:6px;">
              <span class="badge badge-tag">Q${idx + 1} · ${esc(q.category)}</span>
              ${state.quizScore[q.id] === true ? `<span class="badge badge-verified">CONFIDENT</span>` : state.quizScore[q.id] === false ? `<span class="badge badge-assumption">REVIEW AGAIN</span>` : ""}
            </div>
            <h3 style="margin-bottom:6px;">${esc(q.question)}</h3>
            <details class="disclosure">
              <summary>Reveal Answer &amp; Source Citation</summary>
              <div class="disclosure-body">
                <p>${esc(q.answer)}</p>
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-top:8px;">
                  <span class="file-ref">${esc(q.ref)}</span>
                  <div style="display:flex;gap:6px;">
                    <button class="btn btn-sm" data-qmark="${esc(q.id)}" data-val="1">✓ Got it</button>
                    <button class="btn btn-sm" data-qmark="${esc(q.id)}" data-val="0">↺ Review again</button>
                  </div>
                </div>
              </div>
            </details>
          </article>`
        ).join("")}
      `;
      document.getElementById("quiz-reset").onclick = () => { state.quizScore = {}; renderLearning(); };
      host.querySelectorAll("[data-qmark]").forEach((btn) => {
        btn.onclick = () => {
          state.quizScore[btn.dataset.qmark] = btn.dataset.val === "1";
          renderLearning();
        };
      });
    }
  }

  function initLearning() {
    document.querySelectorAll("#learning-tabs .pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.learningSub = btn.dataset.sub;
        document.querySelectorAll("#learning-tabs .pill").forEach((b) => b.classList.toggle("active", b === btn));
        renderLearning();
      });
    });
    renderLearning();
  }

  // ---------- VIEW 6: PROVENANCE & TESTS ----------
  function renderProvenance() {
    const t = META.verifiedTests || { command: "", passed: 0, failed: 0, durationSeconds: 0, files: [] };
    document.getElementById("provenance-stage").innerHTML = `
      <div class="two-col" style="margin-bottom:14px;">
        <div class="wt-card">
          <h3>Git Snapshot Recorded</h3>
          <table class="data-table">
            <tr><th>Commit SHA</th><td><code>${esc(META.commit)}</code></td></tr>
            <tr><th>Branch</th><td><code>${esc(META.branch)}</code></td></tr>
            <tr><th>Commit Subject</th><td>${esc(META.subject)}</td></tr>
            <tr><th>Commit Date</th><td><code>${esc(META.commitDate)}</code></td></tr>
            <tr><th>Atlas Generated</th><td><code>${esc(META.generatedAt)}</code></td></tr>
            <tr><th>Verbatim Excerpts</th><td>${Object.keys(EXCERPTS).length} slices extracted directly from repository files</td></tr>
          </table>
        </div>
        <div class="wt-card">
          <h3>Verified Local Test Execution</h3>
          <p class="muted">Command: <code>${esc(t.command)}</code></p>
          <div class="kv-grid">
            <div class="kv-box"><div class="kv-label">Passed</div><div class="kv-val" style="color:var(--ok);">${t.passed}</div></div>
            <div class="kv-box"><div class="kv-label">Failed</div><div class="kv-val">${t.failed}</div></div>
            <div class="kv-box"><div class="kv-label">Duration</div><div class="kv-val">${t.durationSeconds}s</div></div>
          </div>
          <ul style="margin:6px 0 0 18px;padding:0;font-size:12.5px;">
            ${(t.files || []).map((f) => `<li><code>${esc(f)}</code></li>`).join("")}
          </ul>
        </div>
      </div>
      <div class="wt-card">
        <h3>How Evidence Levels Are Distinguished Throughout This Atlas</h3>
        <table class="data-table">
          <thead><tr><th>Badge</th><th>Meaning</th><th>Examples in This Repo</th></tr></thead>
          <tbody>
            <tr>
              <td>${badgeHtml("verified")}</td>
              <td>Behavior observed directly by executing the repository's 50-test <code>unittest</code> suite against commit <code>${esc(META.short)}</code>.</td>
              <td><code>read_file</code>/<code>search_text</code> security &amp; budgets, <code>conversation_turn</code> rollback on Esc/Ctrl-C, atomic <code>save_settings</code>, <code>StreamCell</code> char-by-char Markdown equivalence, <code>AgentTui</code> scrolling &amp; Ctrl-T pager, <code>scripts/run_model.py</code> flag construction.</td>
            </tr>
            <tr>
              <td>${badgeHtml("static")}</td>
              <td>Deduced from reading verbatim source files without executing that specific code path or edge condition at runtime.</td>
              <td>Shallow-copy caveat on <code>messages.copy()</code> if a future hook mutates dicts in place; default <code>AGENT_BASE_URL</code> wiring between <code>agent.py</code> and <code>llama-server</code>.</td>
            </tr>
            <tr>
              <td>${badgeHtml("assumption")}</td>
              <td>External runtime behavior owned by Strands SDK, OpenAI client, or a live <code>llama-server</code> Vulkan/CPU process (not started in unit tests).</td>
              <td>SSE wire format from <code>POST /v1/chat/completions</code>, Gemma 4 Jinja tool-call quality, HTTP 400 behavior on context exhaustion with <code>--no-context-shift</code>.</td>
            </tr>
          </tbody>
        </table>
      </div>
    `;
  }

  // ---------- BOOT ----------
  initMeta();
  initNav();
  initC4();
  initInventory();
  renderWalkthroughs();
  renderTutorial();
  initLabs();
  initLearning();
  renderProvenance();
})();
