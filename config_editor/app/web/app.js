"use strict";

// ---- API bridge ------------------------------------------------------------
const api = () => window.pywebview.api;

const state = {
  schema: null,
  values: {},
  activeSection: null,
  issuesByPath: {},   // path -> level
  dirty: false,
};

// ---- dotted-path helpers ---------------------------------------------------
function getVal(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function setVal(obj, path, value) {
  const parts = path.split(".");
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== "object" || cur[parts[i]] === null) cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}

// ---- status / meta ---------------------------------------------------------
function setStatus(msg, kind = "") {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = "status" + (kind ? " " + kind : "");
}
function setMeta() {
  document.getElementById("meta").textContent =
    `schema ${state.schema?.schema_version ?? "?"}` + (state.dirty ? " • unsaved changes" : "");
}
function markDirty() { state.dirty = true; setMeta(); }

// ---- sidebar ---------------------------------------------------------------
function renderSidebar() {
  const nav = document.getElementById("sidebar");
  nav.innerHTML = "";
  for (const sec of state.schema.sections) {
    const item = document.createElement("div");
    item.className = "nav-item" + (sec.key === state.activeSection ? " active" : "");
    item.dataset.section = sec.key;
    const errs = countSectionIssues(sec);
    item.innerHTML = `<span>${sec.label}</span>` + (errs ? `<span class="badge">${errs}</span>` : "");
    item.onclick = () => { state.activeSection = sec.key; renderSidebar(); renderSection(); };
    nav.appendChild(item);
  }
}
function countSectionIssues(sec) {
  let n = 0;
  for (const f of iterFields([sec])) if (state.issuesByPath[f.path] === "error") n++;
  return n;
}

// ---- field iteration -------------------------------------------------------
function* iterFields(nodes) {
  for (const n of nodes) {
    if (n.kind === "field") yield n;
    else if (n.kind === "group") yield* iterFields(n.children);
    // collection nodes have an item_template, not concrete fields -> skip
  }
}

// ---- section/form rendering ------------------------------------------------
function renderSection() {
  const sec = state.schema.sections.find((s) => s.key === state.activeSection);
  const header = document.getElementById("section-header");
  header.innerHTML = `<h1>${escapeHtml(sec.label)}</h1>` +
    (sec.help ? `<p>${escapeHtml(sec.help)}</p>` : "");

  if (sec.key === "aws") {
    const actions = document.createElement("div");
    actions.className = "section-actions";
    const check = document.createElement("button");
    check.type = "button";
    check.id = "btn-check-aws";
    check.className = "btn-check-aws";
    check.textContent = "Check AWS auth";
    check.onclick = doCheckAws;
    const setkr = document.createElement("button");
    setkr.type = "button";
    setkr.className = "btn-check-aws";
    setkr.textContent = "Set keyring credentials…";
    setkr.onclick = doSetKeyring;
    actions.appendChild(check);
    actions.appendChild(setkr);
    header.appendChild(actions);
  }

  const guide = document.getElementById("section-guide");
  guide.innerHTML = sec.doc
    ? `<div class="guide-head">Section guide</div><pre>${escapeHtml(sec.doc)}</pre>`
    : `<div class="guide-empty">No additional documentation for this section.</div>`;
  // Paths that control a @when condition in this section -> changing them re-renders.
  state.controllers = new Set();
  for (const fld of iterFields([sec])) {
    if (fld.when) state.controllers.add(fld.when.path);
  }

  const form = document.getElementById("form");
  form.innerHTML = "";
  renderNodes(sec.children, form);
}

function renderNodes(nodes, container) {
  for (const node of nodes) {
    if (node.kind === "group") {
      const g = document.createElement("div");
      g.className = "group";
      g.innerHTML = `<div class="group-label">${escapeHtml(node.label)}</div>`;
      container.appendChild(g);
      renderNodes(node.children, container);
    } else if (node.kind === "collection") {
      container.appendChild(renderCollection(node));
    } else {
      container.appendChild(renderField(node));
    }
  }
}

// ---- repeatable collections ------------------------------------------------
function singular(node) { return node.key.replace(/_fields$/, "").replace(/s$/, "") || "entry"; }

function newItemKey(node, entries) {
  const prefix = node.key.replace(/_fields$/, "") || "item";
  let n = Object.keys(entries).length + 1;
  while (entries[prefix + n] !== undefined) n++;
  return prefix + n;
}

function renderCollection(node) {
  const wrap = document.createElement("div");
  wrap.className = "group collection";
  wrap.innerHTML = `<div class="group-label">${escapeHtml(node.label)}</div>` +
    (node.help ? `<div class="coll-help">${escapeHtml(node.help)}</div>` : "");

  const itemsEl = document.createElement("div");
  itemsEl.className = "items";
  wrap.appendChild(itemsEl);

  const add = document.createElement("button");
  add.type = "button";
  add.className = "btn-add";
  add.textContent = `+ Add ${singular(node)}`;
  add.onclick = () => { addItem(node); rebuild(); markDirty(); };
  wrap.appendChild(add);

  function rebuild() {
    itemsEl.innerHTML = "";
    const entries = getVal(state.values, node.path) || {};
    const keys = Object.keys(entries);
    if (!keys.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No entries yet.";
      itemsEl.appendChild(empty);
    }
    for (const itemKey of keys) itemsEl.appendChild(renderItem(node, itemKey, rebuild));
  }
  rebuild();
  return wrap;
}

function renderItem(node, itemKey, rebuild) {
  const card = document.createElement("div");
  card.className = "item-card";

  const head = document.createElement("div");
  head.className = "item-head";
  const title = document.createElement("span");
  title.className = "item-title";
  const labelVal = getVal(state.values, `${node.path}.${itemKey}.${node.item_label_field}`);
  title.textContent = labelVal || itemKey;
  const rm = document.createElement("button");
  rm.type = "button";
  rm.className = "btn-remove";
  rm.textContent = "Remove";
  rm.onclick = () => {
    const entries = getVal(state.values, node.path) || {};
    delete entries[itemKey];
    markDirty();
    rebuild();
  };
  head.appendChild(title);
  head.appendChild(rm);
  card.appendChild(head);

  for (const tpl of node.item_template) {
    const f = Object.assign({}, tpl, { path: `${node.path}.${itemKey}.${tpl.key}` });
    const fieldEl = renderField(f);
    card.appendChild(fieldEl);
    if (tpl.key === node.item_label_field) {
      const inp = fieldEl.querySelector("input, select, textarea");
      if (inp) inp.addEventListener("input", () => { title.textContent = inp.value || itemKey; });
    }
  }
  return card;
}

function addItem(node) {
  let entries = getVal(state.values, node.path);
  if (!entries || typeof entries !== "object") { entries = {}; setVal(state.values, node.path, entries); }
  const key = newItemKey(node, entries);
  const item = {};
  for (const tpl of node.item_template) item[tpl.key] = tpl.default;
  entries[key] = item;
}

function whenActive(f) {
  if (!f.when) return true;
  const cur = getVal(state.values, f.when.path);
  return f.when.values.map(String).includes(String(cur));
}

function whenNote(f) {
  const ctrl = f.when.path.split(".").pop();
  return `Not used — only when ${ctrl} is ${f.when.values.join(" or ")}.`;
}

function renderField(f) {
  const active = whenActive(f);
  const wrap = document.createElement("div");
  wrap.className = "field" + (active && state.issuesByPath[f.path] ? " invalid" : "") +
    (active ? "" : " disabled");
  wrap.dataset.path = f.path;

  const label = document.createElement("div");
  label.className = "label";
  label.innerHTML = `<span class="name">${escapeHtml(f.label)}</span>` +
    `<span class="path" title="${escapeHtml(f.path)}">${escapeHtml(f.path)}</span>`;

  const control = document.createElement("div");
  control.className = "control";
  control.appendChild(buildInput(f));
  if (!active) {
    control.querySelectorAll("input, select, textarea").forEach((el) => { el.disabled = true; });
    const note = document.createElement("div");
    note.className = "hint when-note";
    note.textContent = whenNote(f);
    control.appendChild(note);
  } else if (f.help) {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = f.help;
    control.appendChild(hint);
  }

  wrap.appendChild(label);
  wrap.appendChild(control);
  return wrap;
}

// Re-render the section when a field that controls a @when condition changes.
function maybeReact(path) {
  if (state.controllers && state.controllers.has(path)) renderSection();
}

function buildInput(f) {
  const val = getVal(state.values, f.path);

  if (f.widget === "checkbox") {
    const lbl = document.createElement("label");
    lbl.className = "switch";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!val;
    cb.onchange = () => { setVal(state.values, f.path, cb.checked); markDirty(); maybeReact(f.path); };
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(cb.checked ? "Enabled" : "Disabled"));
    cb.addEventListener("change", () => { lbl.lastChild.textContent = cb.checked ? "Enabled" : "Disabled"; });
    return lbl;
  }

  if (f.widget === "select") {
    const sel = document.createElement("select");
    const choices = f.choices || [];
    // ensure the current value is selectable even if outside the declared set
    const opts = choices.includes(val) || val == null ? choices : [val, ...choices];
    for (const c of opts) {
      const o = document.createElement("option");
      o.value = c; o.textContent = c;
      if (c === val) o.selected = true;
      sel.appendChild(o);
    }
    sel.onchange = () => { setVal(state.values, f.path, sel.value); markDirty(); maybeReact(f.path); };
    return sel;
  }

  if (f.widget === "number") {
    const inp = document.createElement("input");
    inp.type = "number";
    if (f.step != null) inp.step = f.step; else inp.step = f.type === "int" ? "1" : "any";
    if (f.min != null) inp.min = f.min;
    if (f.max != null) inp.max = f.max;
    inp.value = val ?? "";
    inp.oninput = () => {
      const v = inp.value === "" ? null : (f.type === "int" ? parseInt(inp.value, 10) : parseFloat(inp.value));
      setVal(state.values, f.path, Number.isNaN(v) ? null : v); markDirty();
    };
    return inp;
  }

  if (f.widget === "list") {
    const ta = document.createElement("textarea");
    ta.value = Array.isArray(val) ? val.join("\n") : (val ?? "");
    ta.placeholder = "one item per line";
    ta.oninput = () => {
      const items = ta.value.split("\n").map((s) => s.trim()).filter(Boolean);
      setVal(state.values, f.path, items); markDirty();
    };
    return ta;
  }

  if (f.widget === "textarea") {
    const ta = document.createElement("textarea");
    ta.value = val ?? "";
    ta.oninput = () => { setVal(state.values, f.path, ta.value); markDirty(); };
    return ta;
  }

  // text (optionally with editable suggestions)
  const inp = document.createElement("input");
  inp.type = f.widget === "secret" ? "password" : "text";
  inp.value = val ?? "";
  if (f.choices && f.choices.length) {
    const id = "dl_" + f.path.replace(/[^a-z0-9]/gi, "_");
    inp.setAttribute("list", id);
    const dl = document.createElement("datalist");
    dl.id = id;
    for (const c of f.choices) {
      const o = document.createElement("option"); o.value = c; dl.appendChild(o);
    }
    inp.appendChild(dl);
  }
  inp.oninput = () => {
    setVal(state.values, f.path, inp.value === "" && f.type === "null" ? null : inp.value);
    markDirty();
  };
  return inp;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---- actions ---------------------------------------------------------------
async function doNew() {
  const profile = document.getElementById("profile-select").value || null;
  const res = await api().new_config(profile);
  state.values = res.values;
  state.dirty = false;
  document.getElementById("btn-upgrade").classList.add("hidden");
  state.issuesByPath = {};
  renderAll();
  setStatus(profile ? `New config from profile “${profile}”.` : "New config from sample defaults.", "ok");
}

async function doOpen() {
  const path = await api().open_dialog();
  if (!path) return;
  const res = await api().open_config(path);
  state.values = res.values;
  state.dirty = false;
  state.issuesByPath = {};
  document.getElementById("btn-upgrade").classList.toggle("hidden", !res.needs_upgrade);
  renderAll();
  setStatus(`Opened ${res.path}` + (res.needs_upgrade ? " — needs upgrade." : "."),
            res.needs_upgrade ? "warn" : "ok");
}

async function doValidate() {
  const issues = await api().validate(state.values);
  state.issuesByPath = {};
  for (const i of issues) {
    const prev = state.issuesByPath[i.path];
    if (i.level === "error" || prev == null) state.issuesByPath[i.path] = i.level;
  }
  renderIssues(issues);
  renderSidebar();
  renderSection();
  const errs = issues.filter((i) => i.level === "error").length;
  const warns = issues.filter((i) => i.level === "warning").length;
  setStatus(errs ? `${errs} error(s), ${warns} warning(s).` : `Valid. ${warns} warning(s).`,
            errs ? "err" : warns ? "warn" : "ok");
}

function renderIssues(issues) {
  const panel = document.getElementById("issues");
  const list = document.getElementById("issues-list");
  list.innerHTML = "";
  if (!issues.length) { panel.classList.add("hidden"); return; }
  for (const i of issues) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="tag ${i.level}">${i.level}</span>` +
      `<div><div class="msg">${escapeHtml(i.message)}</div><div class="where">${i.path}</div></div>`;
    li.onclick = () => navigateTo(i.path);
    list.appendChild(li);
  }
  panel.classList.remove("hidden");
}

function navigateTo(path) {
  const top = path.split(".")[0];
  const sec = state.schema.sections.find((s) => s.key === top) ||
              state.schema.sections.find((s) => s.key === "general");
  if (sec) { state.activeSection = sec.key; renderSidebar(); renderSection(); }
  const el = document.querySelector(`.field[data-path="${CSS.escape(path)}"]`);
  if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); el.querySelector("input,select,textarea")?.focus(); }
}

function openModal(title, { confirm = false, confirmText = "OK" } = {}) {
  document.getElementById("modal-title").textContent = title;
  const cbtn = document.getElementById("modal-confirm");
  cbtn.classList.toggle("hidden", !confirm);
  cbtn.textContent = confirmText;
  document.getElementById("modal-cancel").textContent = confirm ? "Cancel" : "Close";
  document.getElementById("modal").classList.remove("hidden");
}

async function doCheckAws() {
  const btn = document.getElementById("btn-check-aws");
  const label = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Checking…"; }
  setStatus("Checking AWS auth (contacting AWS)…");
  let res;
  try {
    res = await api().check_aws(state.values);
  } catch (e) {
    setStatus("AWS check failed: " + (e && e.message ? e.message : e), "err");
    return;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = label; }
  }
  const body = document.getElementById("modal-body");
  body.innerHTML = `<div class="aws-summary">${escapeHtml(res.summary)}</div>` +
    res.checks.map((c) =>
      `<div class="check-row"><span class="tag ${c.status}">${c.status}</span>` +
      `<div><div class="check-name">${escapeHtml(c.name)}</div>` +
      (c.detail ? `<div class="check-detail">${escapeHtml(c.detail)}</div>` : "") +
      `</div></div>`).join("");
  openModal("AWS auth check");
  const errs = res.checks.filter((c) => c.status === "error").length;
  const warns = res.checks.filter((c) => c.status === "warn").length;
  setStatus(res.summary, errs ? "err" : warns ? "warn" : "ok");
}

function doSetKeyring() {
  const svc = getVal(state.values, "aws.keyring_service_name") || "rmi_s3";
  document.getElementById("modal-body").innerHTML =
    `<div class="kr-form">` +
    `<label>Keyring service<input id="kr-svc" type="text" value="${escapeHtml(svc)}"></label>` +
    `<label>Access Key ID<input id="kr-ak" type="text" autocomplete="off" spellcheck="false"></label>` +
    `<label>Secret Access Key<input id="kr-sk" type="password" autocomplete="off"></label>` +
    `<div class="kr-note">Stored in the OS keyring on this machine — never written to config.yaml.</div>` +
    `</div>`;
  openModal("Set AWS keyring credentials", { confirm: true, confirmText: "Save to keyring" });
  document.getElementById("modal-confirm").onclick = async () => {
    const svcv = document.getElementById("kr-svc").value.trim();
    const ak = document.getElementById("kr-ak").value.trim();
    const sk = document.getElementById("kr-sk").value;
    if (!ak || !sk) { setStatus("Access Key ID and Secret are both required.", "err"); return; }
    let res;
    try { res = await api().set_keyring(svcv, ak, sk); }
    catch (e) { setStatus("Set keyring failed: " + (e && e.message ? e.message : e), "err"); return; }
    document.getElementById("modal").classList.add("hidden");
    setStatus((res.status === "ok" ? "✓ " : "✗ ") + res.detail, res.status === "ok" ? "ok" : "err");
  };
}

async function doUpgrade() {
  const res = await api().upgrade(state.values);
  const r = res.report;
  const body = document.getElementById("modal-body");
  body.innerHTML =
    `<div class="row"><span>Version</span><strong>${r.source_version} → ${r.target_version}</strong></div>` +
    `<div class="row"><span>Keys carried over</span><strong>${r.carried_over}</strong></div>` +
    `<div class="row"><span>New keys (defaults filled)</span><strong>${r.added_keys.length}</strong></div>` +
    `<div class="row"><span>Removed keys</span><strong>${r.removed_keys.length}</strong></div>` +
    `<div class="row"><span>Renamed</span><strong>${r.renamed.length}</strong></div>` +
    detailsList("Added", r.added_keys) + detailsList("Removed", r.removed_keys) + detailsList("Renamed", r.renamed);
  openModal("Upgrade", { confirm: true, confirmText: "Apply upgrade" });
  const modal = document.getElementById("modal");
  document.getElementById("modal-confirm").onclick = () => {
    state.values = res.values;
    state.issuesByPath = {};
    markDirty();
    document.getElementById("btn-upgrade").classList.add("hidden");
    renderAll();
    modal.classList.add("hidden");
    setStatus(`Upgraded to ${r.target_version}. Review and Save.`, "ok");
  };
}
function detailsList(title, items) {
  if (!items.length) return "";
  return `<details><summary>${title} (${items.length})</summary>` +
    items.map((k) => `<div><code>${escapeHtml(k)}</code></div>`).join("") + "</details>";
}

async function doPreview() {
  const drawer = document.getElementById("preview");
  if (!drawer.classList.contains("hidden")) { drawer.classList.add("hidden"); return; }
  document.getElementById("preview-body").textContent = await api().preview(state.values);
  drawer.classList.remove("hidden");
}

async function doSave() {
  await doValidate();
  const path = await api().save_dialog("config.yaml");
  if (!path) return;
  const res = await api().save(state.values, path);
  if (res.ok) { state.dirty = false; setMeta(); setStatus(`Saved ${res.path}`, "ok"); }
}

// ---- bootstrap -------------------------------------------------------------
function renderAll() { renderSidebar(); renderSection(); setMeta(); }

async function init() {
  state.schema = await api().get_schema();
  const profiles = await api().list_profiles();
  const sel = document.getElementById("profile-select");
  for (const p of profiles) {
    const o = document.createElement("option");
    o.value = p.name; o.textContent = `${p.name} (${p.source})`;
    sel.appendChild(o);
  }
  state.activeSection = state.schema.sections[0]?.key;
  await doNew();

  document.getElementById("btn-new").onclick = doNew;
  document.getElementById("btn-open").onclick = doOpen;
  document.getElementById("btn-validate").onclick = doValidate;
  document.getElementById("btn-upgrade").onclick = doUpgrade;
  document.getElementById("btn-preview").onclick = doPreview;
  document.getElementById("btn-save").onclick = doSave;
  document.getElementById("btn-preview-close").onclick = () => document.getElementById("preview").classList.add("hidden");
  document.getElementById("btn-issues-close").onclick = () => document.getElementById("issues").classList.add("hidden");
  document.getElementById("modal-cancel").onclick = () => document.getElementById("modal").classList.add("hidden");
}

async function start() {
  try {
    await init();
  } catch (e) {
    const msg = e && e.message ? e.message : String(e);
    setStatus("Failed to load: " + msg, "err");
    console.error("Config editor init failed:", e);
  }
}

// Start as soon as the API bridge is available; fall back to the pywebview event.
if (window.pywebview && window.pywebview.api) {
  start();
} else {
  window.addEventListener("pywebviewready", start);
}
