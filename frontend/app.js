/**
 * MATLAB R2026b WebUI Client — Reconstrucción REA v6.5.0
 * Implementa el cliente para el canal mw-mvm/impl/Connection descubierto en ui/jsconsole.
 */

const state = {
  scripts: [],
  activeScript: null,
  figures: [],
  activeFigureNumber: null,
  history: [],
  historyCursor: -1,
  builtinNames: [],
  workspaceNames: [],
  busy: false,
};

const COPILOT_TEMPLATES = [
  {
    title: "Descomposición Espectral y Autovalores",
    desc: "Calcula autovalores, SVD, determinante y número de condición de una matriz simétrica.",
    code: "A = [4 -1 1; -1 4.25 2.75; 1 2.75 3.5]\n[V, D] = eig(A)\n[U, S, W] = svd(A)\ncond_A = cond(A)",
  },
  {
    title: "Atractor y Ciclo Límite con ode45",
    desc: "Integra un sistema dinámico no lineal de segundo orden mediante Runge-Kutta de 4º/5º orden.",
    code: "mu = 1.8;\nvdp = @(t, y) [y(2); mu * (1 - y(1)^2) * y(2) - y(1)];\n[t, Y] = ode45(vdp, [0, 20], [2.0, 0.0]);\nfigure(1); clf;\nplot(Y(:, 1), Y(:, 2), 'c-');\ntitle('Ciclo Límite Van der Pol'); xlabel('y_1'); ylabel('y_2');",
  },
  {
    title: "Ajuste Polinomial (polyfit / polyval)",
    desc: "Ajusta un polinomio cúbico por mínimos cuadrados y grafica los datos frente al modelo.",
    code: "x = linspace(0, 5, 30);\ny = 0.5 * x.^3 - 2 * x.^2 + x + 3 + 0.8 * randn(1, 30);\np = polyfit(x, y, 3)\ny_fit = polyval(p, x);\nfigure(1); clf;\nscatter(x, y);\nhold on;\nplot(x, y_fit, 'r-');\ntitle('Regresión Polinomial Grado 3'); legend('Datos', 'Ajuste polyfit');",
  },
  {
    title: "Superficie 3D y Mapa de Calor (surf + imagesc)",
    desc: "Genera la función matricial peaks(40) y visualiza su topología 3D y proyección de intensidad.",
    code: "[X, Y, Z] = peaks(40);\nfigure(2); clf;\nsubplot(1, 2, 1); surf(X, Y, Z); colormap('turbo'); title('surf(X,Y,Z)');\nsubplot(1, 2, 2); imagesc(Z); colormap('turbo'); colorbar(); title('imagesc(Z)');",
  },
];

async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ---------- Command Window: render con paridad MATLAB R2026b ----------
   Colores reales extraídos del webgui de R2026b (index-css.css + bundle.361.js):
   prompt ">> " cobalt600 #0E00FF · salida gray900 #212121 · error #E11B14
   (--mw-color-matlabErrors red550) · warning #B36205 (--mw-color-matlabWarning
   honey550) · hyperlinks azul. */

const CW_SEGMENT_CLASS = {
  out: "cw-out",
  warn: "cw-warn",
  err: "cw-err",
};

const CW_LINK_RE = /> In ([A-Za-z_][\w.]*) \(line (\d+)\)/g;

function cwOutput() {
  return document.getElementById("command-output");
}

function cwPromptline() {
  return document.getElementById("cw-promptline");
}

function cwInput() {
  return document.getElementById("command-input");
}

function cwInsertBeforePrompt(el) {
  const out = cwOutput();
  out.insertBefore(el, cwPromptline());
  out.scrollTop = out.scrollHeight;
}

function cwWarnSpan(text) {
  /* "> In <func> (line <n>)" se renderiza como hyperlink azul, como en MATLAB */
  const span = document.createElement("span");
  let last = 0;
  for (const m of text.matchAll(CW_LINK_RE)) {
    span.appendChild(document.createTextNode(text.slice(last, m.index)));
    const link = document.createElement("span");
    link.className = "cw-link";
    link.textContent = m[0];
    span.appendChild(link);
    last = m.index + m[0].length;
  }
  span.appendChild(document.createTextNode(text.slice(last)));
  return span;
}

function appendConsoleEntry(code, res) {
  const echo = document.createElement("div");
  echo.className = "cw-entry cw-echo-line";
  const mark = document.createElement("span");
  mark.className = "cw-promptmark";
  mark.textContent = ">> ";
  const cmd = document.createElement("span");
  cmd.className = "cw-echo-text";
  cmd.textContent = code;
  echo.append(mark, cmd);
  cwInsertBeforePrompt(echo);

  let segments = (res && res.segments) || [];
  if (!segments.length && res) {
    if (res.output) segments.push({ kind: "out", text: res.output });
    if (res.error) segments.push({ kind: "err", text: res.error });
  }
  for (const seg of segments) {
    if (!seg.text) continue;
    const div = document.createElement("div");
    div.className = `cw-entry ${CW_SEGMENT_CLASS[seg.kind] || "cw-out"}`;
    if (seg.kind === "warn") {
      div.appendChild(cwWarnSpan(seg.text));
    } else {
      div.textContent = seg.text;
    }
    cwInsertBeforePrompt(div);
  }

  /* clc: la Command Window queda vacía, incluido el propio eco de `clc` */
  const events = (res && res.events) || [];
  if (events.some((ev) => ev && ev.type === "clc")) {
    cwOutput().querySelectorAll(".cw-entry").forEach((n) => n.remove());
  }
}

function setBusy(busy) {
  state.busy = busy;
  const promptline = cwPromptline();
  const input = cwInput();
  if (promptline) promptline.classList.toggle("busy", busy);
  if (input) {
    input.disabled = busy;
    if (!busy) input.focus();
  }
}

function renderWorkspace(variables) {
  const tbody = document.getElementById("workspace-tbody");
  const countBadge = document.getElementById("workspace-count");
  countBadge.textContent = `${variables.length} vars`;
  tbody.innerHTML = "";

  for (const v of variables) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="ws-name">${v.name}</td>
      <td class="ws-mono">${v.class}</td>
      <td class="ws-mono">${v.size}</td>
      <td class="ws-mono">${v.preview}</td>
    `;
    tr.addEventListener("click", () => inspectVariable(v.name));
    tbody.appendChild(tr);
  }
}

async function inspectVariable(name) {
  try {
    const data = await apiGet(`/api/mvm/variable/${encodeURIComponent(name)}`);
    document.getElementById("inspector-var-name").textContent = `${data.name}`;
    const box = document.getElementById("variable-inspector");
    if (data.matrix_data && data.matrix_data.length > 0) {
      const cols = data.matrix_data[0].length;
      let html = `<table class="matrix-grid"><thead><tr><th>#</th>`;
      for (let c = 1; c <= cols; c++) html += `<th>(:,${c})</th>`;
      html += `</tr></thead><tbody>`;
      data.matrix_data.forEach((row, rIdx) => {
        html += `<tr><th>(${rIdx + 1},:)</th>`;
        row.forEach((cell) => {
          html += `<td>${cell}</td>`;
        });
        html += `</tr>`;
      });
      html += `</tbody></table>`;
      box.innerHTML = html;
    } else {
      box.innerHTML = `<pre>${data.formatted}</pre>`;
    }
  } catch (err) {
    console.error(err);
  }
}

function renderFigures(figures) {
  state.figures = figures || [];
  const tabsEl = document.getElementById("figure-tabs");
  const viewport = document.getElementById("figure-viewport");
  tabsEl.innerHTML = "";

  if (state.figures.length === 0) {
    viewport.innerHTML = `
      <div class="empty-figure">
        <p>Sin figuras activas.</p>
        <span>Ejecuta <code>spectral_fft.m</code>, <code>surface_peaks_3d.m</code> o usa <code>plot(...)</code> / <code>surf(...)</code>.</span>
      </div>`;
    return;
  }

  if (!state.figures.some((f) => f.figure_number === state.activeFigureNumber)) {
    state.activeFigureNumber = state.figures[state.figures.length - 1].figure_number;
  }

  for (const fig of state.figures) {
    const btn = document.createElement("button");
    btn.className = `fig-tab ${fig.figure_number === state.activeFigureNumber ? "active" : ""}`;
    btn.textContent = `Fig ${fig.figure_number}`;
    btn.addEventListener("click", () => {
      state.activeFigureNumber = fig.figure_number;
      renderFigures(state.figures);
    });
    tabsEl.appendChild(btn);
  }

  const current = state.figures.find((f) => f.figure_number === state.activeFigureNumber) || state.figures[0];
  viewport.innerHTML = `<img src="${current.image_data_url}" alt="MATLAB Figure ${current.figure_number}" />`;
}

async function evaluateCode(code, echoLabel = null) {
  if (!code || !code.trim() || state.busy) return;
  const trimmed = code.trim();
  state.history.push(trimmed);
  state.historyCursor = state.history.length;
  renderCommandHistory();
  setBusy(true);
  setStatus("Busy");
  try {
    const res = await apiPost("/api/mvm/eval", { code });
    appendConsoleEntry(echoLabel || trimmed, res);
    if (res.elapsed_ms !== undefined) {
      document.getElementById("last-exec-latency").textContent = `MVM eval: ${res.elapsed_ms} ms`;
    }
    renderWorkspace(res.workspace || []);
    state.workspaceNames = (res.workspace || []).map((v) => v.name);
    renderFigures(res.figures || []);
    setStatus(res.error ? "Error" : "Ready");
    if (res.workspace && res.workspace.length > 0) {
      inspectVariable(res.workspace[0].name);
    }
  } catch (err) {
    appendConsoleEntry(echoLabel || trimmed, {
      segments: [{ kind: "err", text: `${err.message || err}\n` }],
    });
    setStatus("Error");
  } finally {
    setBusy(false);
  }
}

async function loadScripts() {
  const data = await apiGet("/api/scripts");
  state.scripts = data.scripts || [];
  const listEl = document.getElementById("script-list");
  listEl.innerHTML = "";

  state.scripts.forEach((s, idx) => {
    const li = document.createElement("li");
    li.className = `script-item ${state.activeScript === s.filename || (!state.activeScript && idx === 0) ? "active" : ""}`;
    li.innerHTML = `
      <span class="script-name">${s.filename}</span>
      <span class="script-desc">${s.title}</span>
    `;
    li.addEventListener("click", () => selectScript(s.filename));
    listEl.appendChild(li);
  });

  if (!state.activeScript && state.scripts.length > 0) {
    selectScript(state.scripts[0].filename);
  }
}

function selectScript(filename) {
  const found = state.scripts.find((s) => s.filename === filename);
  if (!found) return;
  state.activeScript = found.filename;
  document.getElementById("active-script-title").textContent = found.filename;
  document.getElementById("matlab-editor").value = found.content;
  syncEditorGutter();
  updateEditorPosition();
  setStatus(`Abierto ${filename}`);
  document.querySelectorAll(".script-item").forEach((el) => {
    el.classList.toggle("active", el.querySelector(".script-name").textContent === filename);
  });
}

async function loadReaLedger() {
  const data = await apiGet("/api/rea/ledger");
  document.getElementById("rea-ledger-count").textContent = `${data.evidence_count} evidencias`;

  const pinvokeTbody = document.getElementById("pinvoke-tbody");
  pinvokeTbody.innerHTML = "";
  const bindings = (data.native_bridge_status && data.native_bridge_status.pinvoke_bindings) || [];
  for (const b of bindings) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="ws-mono">${b.token}</td>
      <td class="ws-mono">${b.member_token}</td>
      <td class="ws-name">${b.import_name}</td>
      <td class="ws-mono">${b.calling_convention} / ${b.char_set}</td>
      <td class="ws-mono" style="color: ${b.symbol_resolved ? "#a3d95b" : "#e04f5f"}">
        ${b.symbol_resolved ? b.memory_address : "No resuelto"}
      </td>
    `;
    pinvokeTbody.appendChild(tr);
  }

  const cardsEl = document.getElementById("rea-evidence-cards");
  cardsEl.innerHTML = "";
  for (const ev of data.evidence || []) {
    const div = document.createElement("div");
    div.className = "evidence-card";
    div.innerHTML = `
      <h4>
        <span>${ev.artifact_name}</span>
        <span class="mono-badge">${ev.format}</span>
      </h4>
      <div class="evidence-meta">ID: ${ev.evidence_id}</div>
      <div class="evidence-meta">SHA-256: ${ev.sha256} (${ev.byte_length.toLocaleString()} bytes)</div>
      <pre class="evidence-summary">${JSON.stringify(ev.summary, null, 2)}</pre>
    `;
    cardsEl.appendChild(div);
  }
}

function initCopilotTemplates() {
  const container = document.getElementById("copilot-templates");
  container.innerHTML = "";
  for (const tpl of COPILOT_TEMPLATES) {
    const card = document.createElement("div");
    card.className = "copilot-card";
    card.innerHTML = `
      <h3>${tpl.title}</h3>
      <p style="color: var(--text-secondary)">${tpl.desc}</p>
      <pre>${tpl.code}</pre>
      <button class="btn-primary">Cargar en Editor y Ejecutar en MVM</button>
    `;
    card.querySelector("button").addEventListener("click", async () => {
      document.getElementById("matlab-editor").value = tpl.code;
      document.getElementById("active-script-title").textContent = "copilot_generated.m";
      switchTab("ide");
      await evaluateCode(tpl.code, "run('copilot_generated.m')");
    });
    container.appendChild(card);
  }
}

/* MATLAB Desktop tabs: HOME/PLOTS cambian la cinta y muestran el escritorio;
   APPS (simulink/copilot) y REA (rea) abren su ventana de app. */
const RIBBON_TABS = ["home", "plots", "apps", "rea"];
const APP_VIEWS = ["simulink", "copilot", "rea"];

function showRibbon(tabId) {
  document.querySelectorAll(".toolstrip-group").forEach((grp) => {
    const on = grp.id === `toolstrip-${tabId}`;
    grp.hidden = !on;
  });
  document.querySelectorAll(".toolstrip-tab").forEach((btn) => {
    const on = btn.dataset.tab === tabId;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function openApp(tabId) {
  document.querySelectorAll(".workspace-view").forEach((view) => {
    const open = view.id === `view-${tabId}`;
    view.classList.toggle("active", open);
  });
}

function showDesktop() {
  document.querySelectorAll(".workspace-view").forEach((view) => {
    view.classList.toggle("active", view.id === "view-ide");
  });
}

/* ---------- Editor: gutter de números de línea + Ln/Col (MATLAB status) ---------- */
function syncEditorGutter() {
  const ta = document.getElementById("matlab-editor");
  const gutter = document.getElementById("editor-gutter");
  if (!ta || !gutter) return;
  const lines = ta.value.split("\n").length;
  let g = "";
  for (let i = 1; i <= lines; i++) g += i + (i < lines ? "\n" : "");
  gutter.textContent = g;
}

function updateEditorPosition() {
  const ta = document.getElementById("matlab-editor");
  if (!ta) return;
  const upTo = ta.value.slice(0, ta.selectionStart);
  const ln = upTo.split("\n").length;
  const col = upTo.length - upTo.lastIndexOf("\n");
  const el1 = document.getElementById("editor-ln");
  const el2 = document.getElementById("editor-col");
  const pos = document.getElementById("status-pos");
  if (el1) el1.textContent = ln;
  if (el2) el2.textContent = col;
  if (pos) pos.textContent = `Ln ${ln}, Col ${col}`;
}

function initEditorSurface() {
  const ta = document.getElementById("matlab-editor");
  if (!ta) return;
  ta.addEventListener("input", () => { syncEditorGutter(); updateEditorPosition(); });
  ta.addEventListener("click", updateEditorPosition);
  ta.addEventListener("keyup", updateEditorPosition);
  ta.addEventListener("scroll", () => {
    const g = document.getElementById("editor-gutter");
    if (g) g.scrollTop = ta.scrollTop;
  });
  ta.addEventListener("keydown", (e) => {
    /* Tab escribe espacios, como en el Editor de MATLAB */
    if (e.key === "Tab") {
      e.preventDefault();
      const s = ta.selectionStart, en = ta.selectionEnd;
      ta.value = ta.value.slice(0, s) + "    " + ta.value.slice(en);
      ta.selectionStart = ta.selectionEnd = s + 4;
      syncEditorGutter();
      updateEditorPosition();
    }
  });
  syncEditorGutter();
  updateEditorPosition();
}

/* ---------- Command History (panel derecho, estilo MATLAB) ---------- */
function renderCommandHistory() {
  const list = document.getElementById("command-history-list");
  if (!list) return;
  list.innerHTML = "";
  const hist = state.history.slice().reverse();
  for (const cmd of hist) {
    const li = document.createElement("li");
    li.textContent = cmd;
    li.title = "Clic para recargar en la consola";
    li.addEventListener("click", async () => {
      const input = document.getElementById("command-input");
      if (input) { input.value = cmd; input.focus(); }
    });
    list.appendChild(li);
  }
  if (hist.length === 0) {
    const li = document.createElement("li");
    li.textContent = "(sin comandos en esta sesión)";
    li.style.cursor = "default";
    li.style.color = "var(--text-muted)";
    list.appendChild(li);
  }
}

/* ---------- Status bar: mensajes estilo MATLAB ---------- */
function setStatus(message) {
  const el = document.getElementById("status-message");
  if (el) el.textContent = message || "Ready";
}

function switchTab(tabId) {
  if (tabId === "ide" || tabId === "home" || tabId === "plots") {
    showDesktop();
    /* map ide -> ribbon home para llamadas antiguas */
    showRibbon(tabId === "plots" ? "plots" : "home");
    return;
  }
  if (APP_VIEWS.includes(tabId)) {
    /* la ventana de app se abre; la cinta queda en su sección */
    openApp(tabId);
    showRibbon(tabId === "rea" ? "rea" : "apps");
    return;
  }
  if (RIBBON_TABS.includes(tabId)) {
    showRibbon(tabId);
    if (tabId === "home" || tabId === "plots") showDesktop();
    return;
  }
  showDesktop();
  showRibbon("home");
}

document.addEventListener("DOMContentLoaded", async () => {
  // Navegación de pestañas del Toolstrip (HOME/PLOTS/APPS/REA)
  document.querySelectorAll(".toolstrip-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Botones de app dentro de las cintas APPS/REA
  document.querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.gotoTab));
  });

  // Botón ✕ de cada ventana de app: vuelve al escritorio
  document.querySelectorAll("[data-close-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchTab("home"));
  });

  // Editor: gutter de números de línea + Ln/Col
  initEditorSurface();

  // Command History: render inicial + botón borrar
  renderCommandHistory();
  const btnClearHist = document.getElementById("btn-clear-history");
  if (btnClearHist) {
    btnClearHist.addEventListener("click", () => {
      state.history = [];
      state.historyCursor = 0;
      renderCommandHistory();
    });
  }

  // Ejecutar Script del Editor
  document.getElementById("btn-run-script").addEventListener("click", async () => {
    const code = document.getElementById("matlab-editor").value;
    const label = `run('${state.activeScript || "editor.m"}')`;
    switchTab("ide");
    await evaluateCode(code, label);
  });

  // Guardar Script
  document.getElementById("btn-save-script").addEventListener("click", async () => {
    const filename = state.activeScript || "custom_script.m";
    const content = document.getElementById("matlab-editor").value;
    await apiPost("/api/scripts", { filename, content });
    await loadScripts();
    appendConsoleEntry(`save('${filename}')`, {
      segments: [{ kind: "out", text: `Archivo '${filename}' guardado correctamente.\n` }],
    });
  });

  // Nuevo Script
  document.getElementById("btn-new-script").addEventListener("click", () => {
    const name = `script_${state.scripts.length + 1}.m`;
    state.activeScript = name;
    document.getElementById("active-script-title").textContent = name;
    document.getElementById("matlab-editor").value = `%% ${name} — Nuevo Script MATLAB R2026b\nA = eye(3)\n`;
  });

  // Chips de demostración rápida
  document.querySelectorAll(".btn-chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      switchTab("ide");
      await evaluateCode(chip.dataset.preset);
    });
  });

  // Limpiar Workspace
  document.getElementById("btn-clear-ws").addEventListener("click", async () => {
    await apiPost("/api/mvm/reset", {});
    renderWorkspace([]);
    renderFigures([]);
    document.getElementById("variable-inspector").innerHTML =
      `<p class="empty-hint">Workspace reiniciado.</p>`;
    appendConsoleEntry("clear; close all", {
      segments: [{ kind: "out", text: "Workspace y figuras limpiados.\n" }],
    });
  });

  // clc: mismo camino que teclear `clc` en el prompt (el motor emite el evento)
  document.getElementById("btn-clc").addEventListener("click", async () => {
    await evaluateCode("clc");
  });

  // ---- Consola interactiva: prompt inline estilo MATLAB ----
  const cmdInput = document.getElementById("command-input");
  const cmdOutput = document.getElementById("command-output");
  const completionPopup = document.getElementById("cw-completion-popup");

  // Clic en la superficie enfoca el prompt (como en MATLAB), salvo selección de texto
  cmdOutput.addEventListener("mouseup", () => {
    if (!window.getSelection().toString() && !state.busy) cmdInput.focus();
  });
  cmdInput.focus();

  const completion = { open: false, items: [], index: 0, tokenStart: 0 };

  function closeCompletion() {
    completion.open = false;
    completionPopup.hidden = true;
  }

  function currentToken() {
    const upto = cmdInput.value.slice(0, cmdInput.selectionStart);
    const m = upto.match(/[A-Za-z_][A-Za-z0-9_]*$/);
    return m ? { text: m[0], start: upto.length - m[0].length } : null;
  }

  function applyCompletion(name, tokenStart) {
    const upto = cmdInput.value.slice(0, cmdInput.selectionStart);
    const rest = cmdInput.value.slice(cmdInput.selectionStart);
    const before = upto.slice(0, tokenStart);
    cmdInput.value = before + name + rest;
    cmdInput.selectionStart = cmdInput.selectionEnd = (before + name).length;
    closeCompletion();
  }

  function openCompletion(items, tokenStart) {
    completion.items = items;
    completion.index = 0;
    completion.tokenStart = tokenStart;
    completionPopup.innerHTML = "";
    items.slice(0, 12).forEach((name, i) => {
      const item = document.createElement("div");
      item.className = "cw-completion-item" + (i === 0 ? " selected" : "");
      item.textContent = name;
      item.addEventListener("mousedown", (e) => {
        e.preventDefault();
        applyCompletion(name, tokenStart);
      });
      completionPopup.appendChild(item);
    });
    if (items.length > 12) {
      const more = document.createElement("div");
      more.className = "cw-completion-more";
      more.textContent = `… ${items.length - 12} más`;
      completionPopup.appendChild(more);
    }
    completionPopup.hidden = false;
    completion.open = true;
  }

  function moveCompletion(delta) {
    const shown = Math.min(completion.items.length, 12);
    completion.index = (completion.index + delta + shown) % shown;
    completionPopup.querySelectorAll(".cw-completion-item").forEach((el, i) => {
      el.classList.toggle("selected", i === completion.index);
    });
  }

  function tabComplete() {
    const token = currentToken();
    if (!token) return;
    const names = [...new Set([...state.workspaceNames, ...state.builtinNames])];
    const matches = names.filter((n) => n.startsWith(token.text) && n !== token.text);
    if (matches.length === 1) {
      applyCompletion(matches[0], token.start);
      return;
    }
    if (matches.length > 1) {
      const lcp = matches.reduce((a, b) => {
        let i = 0;
        while (i < a.length && i < b.length && a[i] === b[i]) i++;
        return a.slice(0, i);
      });
      if (lcp.length > token.text.length) {
        applyCompletion(lcp, token.start);
      } else {
        openCompletion(matches, token.start);
      }
    }
  }

  cmdInput.addEventListener("keydown", async (e) => {
    if (completion.open) {
      if (e.key === "ArrowDown") { e.preventDefault(); moveCompletion(1); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); moveCompletion(-1); return; }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applyCompletion(completion.items[completion.index], completion.tokenStart);
        return;
      }
      if (e.key === "Escape") { e.preventDefault(); closeCompletion(); return; }
      closeCompletion();
    }
    if (e.key === "Tab") {
      e.preventDefault();
      tabComplete();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (state.busy) return;
      const code = cmdInput.value;
      cmdInput.value = "";
      await evaluateCode(code);
    } else if (e.key === "ArrowUp" && state.history.length > 0) {
      e.preventDefault();
      state.historyCursor = Math.max(0, state.historyCursor - 1);
      cmdInput.value = state.history[state.historyCursor] || "";
      cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length);
    } else if (e.key === "ArrowDown" && state.history.length > 0) {
      e.preventDefault();
      state.historyCursor = Math.min(state.history.length, state.historyCursor + 1);
      cmdInput.value = state.history[state.historyCursor] || "";
      cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length);
    }
  });

  // Lista de nombres completables (builtins del motor; opt-in, sin fallo si no existe)
  try {
    const c = await apiGet("/api/mvm/completions");
    state.builtinNames = c.names || [];
  } catch (err) {
    state.builtinNames = [];
  }

  // Simulink PID
  document.getElementById("btn-run-simulink").addEventListener("click", async () => {
    const payload = {
      gain_kp: parseFloat(document.getElementById("sim-kp").value) || 2.4,
      gain_ki: parseFloat(document.getElementById("sim-ki").value) || 1.1,
      gain_kd: parseFloat(document.getElementById("sim-kd").value) || 0.35,
      plant_wn: parseFloat(document.getElementById("sim-wn").value) || 3.2,
      plant_zeta: parseFloat(document.getElementById("sim-zeta").value) || 0.45,
      step_amplitude: 1.0,
      t_final: parseFloat(document.getElementById("sim-tf").value) || 10.0,
    };
    document.getElementById("svg-pid-label").textContent =
      `Kp=${payload.gain_kp}, Ki=${payload.gain_ki}, Kd=${payload.gain_kd}`;
    document.getElementById("svg-plant-label").textContent =
      `ωn=${payload.plant_wn} rad/s, ζ=${payload.plant_zeta}`;

    const res = await apiPost("/api/simulink/simulate", payload);
    document.getElementById("metric-os").textContent = `${res.metrics.overshoot_pct} %`;
    document.getElementById("metric-ts").textContent = `${res.metrics.settling_time_s} s`;
    document.getElementById("metric-ess").textContent = `${res.metrics.steady_state_error}`;
    document.getElementById("metric-peak").textContent = `${res.metrics.peak_value}`;

    renderWorkspace(res.workspace || []);
    renderFigures(res.figures || []);
    const fig4 = (res.figures || []).find((f) => f.figure_number === 4) || (res.figures || [])[0];
    if (fig4) {
      document.getElementById("simulink-figure-box").innerHTML =
        `<img src="${fig4.image_data_url}" alt="Simulink PID Response" />`;
    }
  });

  // Sonda de binarios REA en vivo
  document.getElementById("btn-probe-file").addEventListener("click", async () => {
    const relative_path = document.getElementById("probe-input").value.trim();
    const out = document.getElementById("probe-result");
    try {
      const res = await apiPost("/api/rea/inspect-file", { relative_path });
      out.textContent = JSON.stringify(res, null, 2);
    } catch (err) {
      out.textContent = `Error: ${err.message}`;
    }
  });

  initCopilotTemplates();
  await loadScripts();
  await loadReaLedger();

  // Ejecutar script inicial para poblar el entorno al abrir
  if (state.scripts.length > 0) {
    await evaluateCode(state.scripts[0].content, `run('${state.scripts[0].filename}')`);
  }
});
