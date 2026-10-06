"use strict";
// caland's page. It asks the server on this machine (never anything else), draws what it
// is told as text (never as markup), and holds a secret's value only while it is shown.

const HIDE_AFTER = 30;                 // seconds a shown value stays on the page
const LIMIT = 128 * 1024;              // the most a secret may hold, in bytes
const POLL = 400;                      // ms between looks while a workspace is loading
const STORE = "caland";                // where this tab keeps the session's token
const TOKEN_HEADER = "X-Caland-Token";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...kids.filter((kid) => kid !== null && kid !== ""));
  return node;
};

// ── what the page knows ──────────────────────────────────────────────
let token = null;
let looking = null;       // the next look at the server, while a workspace is loading
let told = null;          // the server's state: phase, who, the scopes
// Maps, not objects: a scope may be called `constructor` or `__proto__`
let keys = new Map();     // scope -> [[key, changed in ms], ...]
let detail = new Map();   // scope -> { access, keyvault, grants }
let scope = null;         // the selected scope's name
let secret = 0;           // the selected secret's place among those shown
let shown = null;         // { scope, key, value, bytes } while a value is on the page
let timer = null, left = 0;
let query = "";
let showAll = false;
let read = null;          // the server's version the names in `keys` are from
// where the keyboard is: one of the three panes, and which button of the detail
let pane = "scopes", action = 0;

// ── asking the server ────────────────────────────────────────────────
class Told extends Error {}
async function ask(path, body) {
  const post = body !== undefined;
  let answer;
  try {
    answer = await fetch(path, {
      method: post ? "POST" : "GET", cache: "no-store",
      headers: { [TOKEN_HEADER]: token ?? "", ...(post ? { "Content-Type": "application/json" } : {}) },
      body: post ? JSON.stringify(body) : undefined,
    });
  } catch {
    trouble("caland is not running any more. Start it again from the terminal.");
    throw new Told("caland is not running");
  }
  if (answer.status === 401) { lock(); throw new Told("no key"); }
  const said = await answer.json().catch(() => ({}));
  if (!answer.ok) throw new Error(said.error || `caland said ${answer.status}`);
  return said;
}
function lock() {
  token = null;
  sessionStorage.removeItem(STORE);
  // nothing it was told stays on a page that is locked: no value, no name
  hide(); clearTimeout(looking);
  told = null; keys = new Map(); detail = new Map(); scope = null;
  for (const id of ["scopes", "secrets", "detail", "code-rows", "host", "who"]) $(id).replaceChildren();
  for (const node of document.querySelectorAll("dialog[open]")) node.close();
  // and nothing that was typed or chosen to be sent: no value, no file
  picked = null; editing = null; moving = null; confirming = null; granting = null;
  for (const id of ["form-value", "form-key", "move-key", "grant-who", "scope-name", "file"]) $(id).value = "";
  for (const id of ["picked", "grants-rows", "confirm-what"]) $(id).replaceChildren();
  $("app").hidden = true; $("locked").hidden = false;
}
function trouble(text) {
  $("trouble").textContent = text;
  $("trouble").hidden = !text;
}
// what goes wrong is said, once, where the person is looking; never thrown away
const carefully = (work) => (...args) => Promise.resolve().then(() => work(...args))
  .catch((error) => { if (!(error instanceof Told)) toast(error.message, true); });

async function enter() {
  const key = location.hash.slice(1);
  if (key) {
    // the key is good once: take it out of the address before anything else
    history.replaceState(null, "", location.pathname);
    try {
      const answer = await fetch("/api/enter", { method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) });
      if (answer.ok) { token = (await answer.json()).token; sessionStorage.setItem(STORE, token); }
    } catch {
      return trouble("caland is not running any more. Start it again from the terminal.");
    }
  }
  // The token this tab kept is for a reload of this page and nothing else. A site the
  // tab went on to can send it back here, or open a window that is handed a copy of what
  // the tab kept: neither is a reload, and both find the page locked.
  const reloaded = performance.getEntriesByType("navigation")[0]?.type === "reload";
  token = token ?? (reloaded ? sessionStorage.getItem(STORE) : null);
  if (!token) return lock();
  $("app").hidden = false;
  await look();
  go("scopes");
}

// ── keeping up with the workspace ────────────────────────────────────
async function look() {
  clearTimeout(looking);
  const first = told === null;
  told = await ask("/api/state");
  if (first) showAll = told.show_all;
  $("host").textContent = told.workspace.host || told.workspace.name;
  $("who").textContent = told.identity ? told.identity.user : "";
  $("read-only").hidden = !told.read_only;
  document.body.dataset.readOnly = String(told.read_only);
  $("version").textContent = `caland ${told.caland}`;
  $("progress").textContent = told.phase === "connecting" ? "Connecting…"
    : told.phase === "loading" ? `Loading scopes… ${told.done}/${told.total}` : "";
  trouble(told.phase === "failed" ? told.error || "The workspace could not be read." : "");

  const names = new Set(told.scopes.map((s) => s.name));
  for (const name of [...keys.keys()]) if (!names.has(name)) { keys.delete(name); detail.delete(name); }
  if (told.phase === "ready" && read !== told.version) {
    // everything has been read: take every name at once, so that filtering never asks
    keys = new Map(Object.entries((await ask("/api/keys")).scopes));
    detail = new Map();
    read = told.version;
  }
  if (!names.has(scope)) { scope = (visibleScopes()[0] ?? {}).name ?? null; secret = 0; }
  await fill(scope);
  draw();
  document.body.dataset.phase = told.phase;   // said last: everything it stands for is drawn
  if (told.phase === "connecting" || told.phase === "loading") looking = setTimeout(carefully(look), POLL);
}
// one scope's secrets and grants, once it has been read
async function fill(name) {
  const row = told.scopes.find((s) => s.name === name);
  if (!row || !row.loaded || detail.has(name)) return;
  const said = await ask(`/api/scope?name=${encodeURIComponent(name)}`);
  keys.set(name, said.secrets);
  detail.set(name, { access: said.access, keyvault: said.keyvault, grants: said.grants });
}
async function refresh(all) {
  if (!told || (!all && !scope)) return;
  const was = told.version;
  await ask("/api/refresh", all ? {} : { scope });
  toast(all ? "Reading the workspace again…" : `Reading ${scope} again…`);
  // what is on the page stays until the server has read: look until its version moves
  for (let tries = 0; tries < 80 && told.version === was; tries += 1) {
    await new Promise((done) => setTimeout(done, 120));
    told = await ask("/api/state");
  }
  await look();
}

// ── what is shown ────────────────────────────────────────────────────
// letters in order, as the terminal version filters
const matches = (text) => {
  let at = 0;
  const lower = text.toLowerCase();
  for (const letter of query.toLowerCase()) { at = lower.indexOf(letter, at) + 1; if (!at) return false; }
  return true;
};
const visibleScopes = () => (told ? told.scopes : []).filter((s) =>
  (showAll || s.access || !s.loaded)
  && (!query || matches(s.name) || (keys.get(s.name) ?? []).some(([key]) => matches(key))));
const visibleSecrets = () => (keys.get(scope) ?? []).filter(([key]) => !query || matches(key) || matches(scope));
const chosen = () => visibleSecrets()[secret];

const day = (ms) => ms ? new Date(ms).toISOString().slice(0, 10) : "—";
const age = (ms) => {
  if (!ms) return "—";
  const days = Math.max(0, Math.floor((Date.now() - ms) / 864e5));
  return days === 0 ? "today" : days === 1 ? "1 day" : `${days} days`;
};
const pill = (permission) => el("span", { textContent: permission || "none",
  className: `state ${["READ", "WRITE", "MANAGE"].includes(permission) ? permission.toLowerCase() : "none"}` });
const facts = (pairs) => el("dl", { className: "facts" },
  ...pairs.flatMap(([term, what]) => [el("dt", { textContent: term }), el("dd", {}, what)]));
function button(label, key, work, kind = "") {
  const node = el("button", { className: kind }, label, key ? " " : null, key ? el("kbd", { textContent: key }) : null);
  node.onclick = carefully(work);
  return node;
}
const mono = (text) => el("span", { className: "mono", textContent: text });
const strong = (text) => el("strong", { textContent: text });
const size = (bytes) => bytes < 1024 ? `${bytes} bytes` : `${(bytes / 1024).toFixed(1)} kB`;
const canChange = () => Boolean(told) && !told.read_only;

function draw() {
  // the lists stay in the page and only their rows are written again, so the keyboard stays
  // where it is; the detail is written whole, and is given the keyboard back if it had it
  const had = $("detail").contains(document.activeElement);
  const scopes = visibleScopes();
  if (scope !== null && !scopes.some((s) => s.name === scope) && scopes.length) {
    scope = scopes[0].name; secret = 0; hide();
    carefully(async () => { await fill(scope); draw(); })();
  }
  $("scopes").replaceChildren(...scopes.map((s, index) => {
    const row = el("li", { role: "option", id: `scope-${index}`, className: s.access || !s.loaded ? "" : "out" },
      el("span", { className: "mono", textContent: s.name }),
      s.keyvault ? el("small", { textContent: "Key Vault" }) : null,
      el("span", { className: "count", textContent: s.loaded ? String(s.count) : "…" }));
    row.setAttribute("aria-selected", String(s.name === scope));
    row.onclick = () => choose(s.name);
    return row;
  }));
  const at = scopes.findIndex((s) => s.name === scope);
  if (at >= 0) $("scopes").setAttribute("aria-activedescendant", `scope-${at}`);
  else $("scopes").removeAttribute("aria-activedescendant");
  const out = told ? told.scopes.length - told.scopes.filter((s) => s.access || !s.loaded).length : 0;
  $("scopes-none").hidden = scopes.length > 0;
  $("scopes-none").textContent = !told || told.phase === "connecting" ? ""
    : query ? "Nothing matches the filter."
    : out && !showAll ? `No scopes you can reach. Press f to show all ${told.scopes.length}.`
    : told.phase === "loading" ? "" : "This workspace has no secret scopes.";

  const rows = visibleSecrets();
  secret = Math.min(secret, Math.max(rows.length - 1, 0));
  $("secrets-title").replaceChildren(...(scope === null ? ["Secrets"]
    : ["Secrets in ", el("span", { className: "mono", textContent: scope })]));
  $("secrets").replaceChildren(...rows.map(([key, changed], index) => {
    const row = el("tr", {}, el("td", { className: "mono", textContent: key }),
      el("td", { className: "num", textContent: day(changed) }), el("td", { className: "num", textContent: age(changed) }));
    row.setAttribute("aria-selected", String(index === secret));
    row.onclick = () => { secret = index; action = 0; hide(); draw(); };
    return row;
  }));
  const row = told ? told.scopes.find((s) => s.name === scope) : null;
  $("secrets-none").hidden = rows.length > 0 || scope === null;
  $("secrets-none").textContent = row && !row.loaded ? "Reading…"
    : (keys.get(scope) ?? []).length ? "Nothing here matches the filter."
    : row && !row.access ? "You have no access to this scope." : "No secrets in this scope.";
  for (const list of [$("scopes"), $("secrets")]) {
    list.querySelector("[aria-selected=true]")?.scrollIntoView({ block: "nearest" });
  }
  drawDetail(rows[secret]);
  rove(had);
}

const hintText = () => `${shown.bytes ? `not text: a file of ${size(shown.bytes)}, shown as base64 · ` : ""}hides in ${left} s`;

function drawDetail(row) {
  const about = detail.get(scope);
  if (scope === null || !about) return $("detail").replaceChildren();
  const you = told.identity ? told.identity.user : "";
  const backed = about.keyvault ? "Azure Key Vault" : "Databricks";
  const may = canChange();
  const access = [el("h2", { textContent: "Who has access" }),
    about.grants.length
      ? el("table", {}, el("tbody", {}, ...about.grants.map(([who, permission]) =>
          el("tr", {}, el("td", { textContent: who === you ? `${who} (you)` : who }), el("td", {}, pill(permission))))))
      : el("p", { className: "none", textContent: "No grants are listed. Listing them takes MANAGE on the scope." }),
    el("div", { className: "acts" }, button(may ? "Change" : "Look closer", "p", openGrants))];
  const whole = may ? [el("h2", { textContent: "Scope" }),
    el("div", { className: "acts" }, button("Delete scope", "", deleteScope, "danger"))] : [];
  if (!row) {
    return $("detail").replaceChildren(el("h2", { textContent: "Scope" }),
      el("div", { className: "name mono", textContent: scope }),
      facts([["Backed by", backed], ["Your access", pill(about.access)]]), ...access, ...whole.slice(1));
  }
  const [key, changed] = row;
  const open = shown && shown.scope === scope && shown.key === key;
  const value = el("pre", { className: `value mono${open ? " shown" : ""}`,
    textContent: open ? shown.value : "•".repeat(16) });
  const hint = el("div", { className: "meta", id: "hint",
    textContent: open ? hintText() : "read from the workspace when you ask, never before" });
  const change = !may ? [] : [el("h2", { textContent: "Change" }), about.keyvault
    ? el("div", {}, el("p", { className: "quiet", textContent: "This scope is Azure Key Vault's: its secrets are changed in Azure. A copy can be taken out." }),
        el("div", { className: "acts" }, button("Copy to…", "m", openMove)))
    : el("div", { className: "acts" }, button("Edit", "e", () => openForm(true)), button("Move or copy", "m", openMove),
        button("Delete", "d", deleteSecret, "danger"))];
  $("detail").replaceChildren(el("h2", { textContent: "Secret" }),
    el("div", { className: "name mono", textContent: key }),
    facts([["Scope", mono(scope)], ["Backed by", backed],
      ["Your access", pill(about.access)],
      ["Last changed", changed ? `${day(changed)} · ${age(changed)}${age(changed) === "today" ? "" : " ago"}` : "—"]]),
    el("h2", { textContent: "Value" }), value, hint,
    el("div", { className: "acts" }, button(open ? "Hide" : "Show", "space", toggle), button("Copy", "c", copy),
      button("Copy as code", "C", openCode)),
    ...change, ...access, ...whole);
}

async function choose(name) {
  scope = name; secret = 0; action = 0; hide();
  draw();
  await fill(name);
  if (scope === name) draw();
}

// ── a value: shown when asked, gone when hidden ──────────────────────
// a value comes as text, or — when it is no text — as the bytes it is, said in base64
const value = (row) => ask("/api/value", { scope, key: row[0] });
const said = (got) => got.binary ? got.base64 : got.value;
async function toggle() {
  const row = chosen();
  if (!row) return;
  if (shown && shown.scope === scope && shown.key === row[0]) { hide(); return draw(); }
  const at = { scope, key: row[0] };
  const got = await value(row);
  if (scope !== at.scope || (chosen() ?? [])[0] !== at.key) return;   // moved on while it came
  shown = { ...at, value: said(got), bytes: got.binary ? got.size : 0 };
  left = HIDE_AFTER;
  clearInterval(timer);
  timer = setInterval(() => {
    left -= 1;
    if (left <= 0) { hide(); draw(); } else if ($("hint")) $("hint").textContent = hintText();
  }, 1000);
  draw();
}
function hide() { shown = null; clearInterval(timer); }
// the value goes from the answer to the clipboard; it is never written into the page
async function put(text) {
  if (window.ClipboardItem && navigator.clipboard?.write) {
    try {
      const blob = Promise.resolve(text).then((t) => new Blob([t], { type: "text/plain" }));
      return await navigator.clipboard.write([new ClipboardItem({ "text/plain": blob })]);
    } catch { /* an older browser: the plain way below */ }
  }
  await navigator.clipboard.writeText(await text);
}
async function copy() {
  const row = chosen();
  if (!row) return;
  let binary = false;
  await put(value(row).then((got) => { binary = Boolean(got.binary); return said(got); }));
  toast(binary ? `Copied ${row[0]} — it is no text, so as base64.` : `Copied ${row[0]}.`);
}

let toasting = null;
function toast(text, bad = false) {
  const node = $("toast");
  node.textContent = text; node.className = bad ? "bad" : ""; node.hidden = false;
  clearTimeout(toasting); toasting = setTimeout(() => { node.hidden = true; }, bad ? 6000 : 3200);
}

// ── how to reach a secret from code ──────────────────────────────────
function openCode() {
  const row = chosen();
  if (!row) return;
  // a name is written as a name, whatever is in it: a string in Python, one word in a shell
  const word = (name) => /^[\w.@-]+$/.test(name) ? name : `'${name.replaceAll("'", "'\\''")}'`;
  const forms = [["Python (dbutils)", `dbutils.secrets.get(scope=${JSON.stringify(scope)}, key=${JSON.stringify(row[0])})`],
    ["Spark conf or a job", `{{secrets/${scope}/${row[0]}}}`],
    ["Databricks CLI", `databricks secrets get-secret ${word(scope)} ${word(row[0])}`]];
  $("code-rows").replaceChildren(...forms.map(([label, code]) => {
    const node = el("button", {}, el("span", { textContent: label }), el("span", { className: "mono", textContent: code }));
    node.onclick = carefully(async () => { await put(code); $("code").close(); toast(`Copied: ${code}`); });
    return node;
  }));
  $("code").showModal();
}

// ── changing things ──────────────────────────────────────────────────
// Everything here asks the server, which refuses what may not be changed whatever this
// page thinks. What goes wrong while a dialog is open is said in the dialog.
function fail(id, error) {
  $(id).textContent = error ? error.message : "";
  $(id).hidden = !error;
}
// after a change: read the workspace again, go to what was changed, and say so
async function changed(toScope, toKey, saying) {
  await look();
  if (toScope && told.scopes.some((s) => s.name === toScope)) {
    scope = toScope; secret = 0;
    await fill(scope);
    const at = toKey ? visibleSecrets().findIndex(([key]) => key === toKey) : -1;
    if (at >= 0) secret = at;
  }
  hide(); draw();
  if (saying) toast(saying);
}
// where a secret can be put: the scopes that are shown, but for Azure's
const targets = () => told.scopes.filter((s) => !s.keyvault && (s.access || showAll));
const options = (rows, picked) => rows.map((s) => el("option", { textContent: s.name, value: s.name, selected: s.name === picked }));

// a secret, new or edited
let editing = null;       // { scope, key } when the form is for a secret that is there
let picked = null;        // { name, base64 } — the file that was chosen
function clearPicked() {
  picked = null; $("file").value = "";
  $("picked").hidden = true; $("picked-note").hidden = true;
}
function openForm(edit) {
  if (!canChange()) return;
  if (edit && (!chosen() || detail.get(scope)?.keyvault)) return;
  if (!targets().length) return toast("There is no scope to put a secret in: make one with N.", true);
  editing = edit ? { scope, key: chosen()[0] } : null;
  $("form-title").textContent = edit ? "Edit secret" : "New secret";
  $("form-scope").replaceChildren(...options(targets(), scope));
  $("form-scope").disabled = $("form-key").disabled = Boolean(edit);
  $("form-key").value = edit ? editing.key : "";
  $("form-value").value = "";
  clearPicked(); fail("form-error");
  $("form").showModal();
  (edit ? $("form-value") : $("form-key")).focus();
}
const base64 = (bytes) => {
  let text = "";
  for (let at = 0; at < bytes.length; at += 0x8000) text += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  return btoa(text);
};
const until = (ms) => {
  const days = Math.round((ms - Date.now()) / 864e5);
  return days > 1 ? `in ${days} days` : days === 1 ? "tomorrow" : days === 0 ? "today"
    : days === -1 ? "expired yesterday" : `expired ${-days} days ago`;
};
// a file that was chosen or dropped: say what it is before it goes anywhere but here
async function take(file) {
  if (!file) return;
  fail("form-error");
  try {
    if (file.size > LIMIT) throw new Error(`${file.name} is ${size(file.size)}: a secret holds 128 kB at most.`);
    const sent = base64(new Uint8Array(await file.arrayBuffer()));
    const what = await ask("/api/describe", { base64: sent });
    picked = { name: file.name, base64: sent };
    $("form-value").value = "";
    const rows = [["Size", size(what.size)], ["Kind", what.kind], ...what.facts];
    if (what.expires) rows.push(["Expires", `${what.expires.slice(0, 10)} · ${until(Date.parse(what.expires))}`]);
    $("picked").replaceChildren(el("div", { className: "name mono", textContent: file.name }), facts(rows));
    $("picked").hidden = false;
    $("picked-note").textContent = what.binary
      ? "Stored byte for byte, and comes out the same. Written nowhere on the way."
      : "Its content becomes the value. Written nowhere on the way.";
    $("picked-note").hidden = false;
    if (!editing && !$("form-key").value) {
      $("form-key").value = file.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9_.@-]+/g, "-");
    }
  } catch (error) {
    if (error instanceof Told) throw error;
    clearPicked(); fail("form-error", error);
  }
}
async function saveForm() {
  const to = editing ? editing.scope : $("form-scope").value;
  const key = $("form-key").value.trim(), text = $("form-value").value;
  try {
    if (!key) throw new Error("Give it a key.");
    if (!picked && !text) {
      throw new Error(editing ? "Type a new value or choose a file. An empty value changes nothing."
        : "Type a value or choose a file.");
    }
    await ask("/api/secret/put", { scope: to, key, new: !editing, ...(picked ? { base64: picked.base64 } : { text }) });
  } catch (error) {
    if (error instanceof Told) throw error;
    return fail("form-error", error);
  }
  $("form-value").value = ""; clearPicked();
  $("form").close();
  await changed(to, key, `Saved ${key}.`);
}

// nothing destructive without a deliberate y
let confirming = null;
function confirmFirst(title, what, note, label, work) {
  $("confirm-title").textContent = title;
  $("confirm-what").replaceChildren(...what);
  $("confirm-note").textContent = note;
  $("confirm-do").textContent = label;
  confirming = work;
  $("confirm").showModal();
  $("confirm-no").focus();
}
function deleteSecret() {
  const row = chosen();
  if (!canChange() || !row) return;
  if (detail.get(scope)?.keyvault) return toast(`${scope} is Azure Key Vault's: its secrets are deleted in Azure.`, true);
  const at = { scope, key: row[0] };
  confirmFirst("Delete secret", [strong("Delete"), " ", mono(at.key), " from ", mono(at.scope), "."],
    "u puts it back, for as long as caland runs and nothing else is deleted.", "Delete", async () => {
      const done = await ask("/api/secret/delete", at);
      await changed(at.scope, null, done.kept ? `Deleted ${at.key} — press u to put it back.`
        : `Deleted ${at.key}. Its value could not be read first, so it cannot be put back.`);
    });
}
function deleteScope() {
  if (!canChange() || scope === null) return;
  const name = scope, count = (keys.get(name) ?? []).length;
  confirmFirst("Delete scope", [strong("Delete"), " scope ", mono(name),
    count ? ` and its ${count} secret${count === 1 ? "" : "s"}.` : ", which is empty."],
    "A scope cannot be put back, and neither can what was in it.", "Delete", async () => {
      await ask("/api/scope/delete", { name });
      await changed(null, null, `Deleted scope ${name}.`);
    });
}
// d deletes what the keyboard is on: a scope in the scopes, a secret anywhere else
const deleteWhat = () => pane === "scopes" || !chosen() ? deleteScope() : deleteSecret();
async function undo() {
  if (!canChange()) return;
  if (!told.taken) return toast("There is nothing to put back.");
  const back = await ask("/api/undo", {});
  await changed(back.scope, back.key, `Put back ${back.scope}/${back.key}.`);
}

// move, copy, rename: one dialog
let moving = null;
function openMove() {
  const row = chosen();
  if (!canChange() || !row) return;
  if (!targets().length) return toast("There is no scope to copy it to.", true);
  const azure = Boolean(detail.get(scope)?.keyvault);
  moving = { scope, key: row[0] };
  $("move-from").textContent = `${scope}/${row[0]}`;
  $("move-scope").replaceChildren(...options(targets(), scope));
  $("move-key").value = row[0];
  $("move-keep").checked = azure; $("move-keep").disabled = azure;   // out of Azure's: a copy is all there is
  fail("move-error");
  $("move").showModal();
  $("move-key").focus(); $("move-key").select();
}
async function saveMove() {
  const to_scope = $("move-scope").value, to_key = $("move-key").value.trim(), keep = $("move-keep").checked;
  try {
    if (!to_key) throw new Error("Give it a key.");
    await ask("/api/secret/move", { ...moving, to_scope, to_key, keep });
  } catch (error) {
    if (error instanceof Told) throw error;
    return fail("move-error", error);
  }
  $("move").close();
  await changed(to_scope, to_key, keep ? `Copied ${moving.key} to ${to_scope}/${to_key}.`
    : `Moved ${moving.key} to ${to_scope}/${to_key} — u puts the original back.`);
}

// who has access to a scope
let granting = null;
function openGrants() {
  if (scope === null || !detail.get(scope)) return;
  granting = scope;
  $("grant-who").value = ""; fail("grants-error");
  drawGrants();
  $("grants").showModal();
}
function drawGrants() {
  const about = detail.get(granting);
  if (!about) return;
  const you = told.identity ? told.identity.user : "";
  $("grants-scope").textContent = granting;
  $("grants-rows").replaceChildren(...about.grants.map(([who, may]) => el("tr", {},
    el("td", { textContent: who === you ? `${who} (you)` : who }), el("td", {}, pill(may)),
    el("td", { className: "end" }, ...(canChange() ? [
      button("Change", "", () => { $("grant-who").value = who; $("grant-may").value = may; $("grant-may").focus(); }), " ",
      button("Remove", "", () => removeGrant(who, who === you), "danger")] : [])))));
  $("grants-none").hidden = about.grants.length > 0;
}
async function regrant(work) {
  try {
    await work();
  } catch (error) {
    if (error instanceof Told) throw error;
    return fail("grants-error", error);
  }
  fail("grants-error");
  await look(); await fill(granting);
  drawGrants(); draw();
}
const giveGrant = () => regrant(async () => {
  const principal = $("grant-who").value.trim(), permission = $("grant-may").value;
  if (!principal) throw new Error("Say who: a user, a group or a service principal.");
  await ask("/api/grant/put", { scope: granting, principal, permission });
  $("grant-who").value = "";
});
function removeGrant(principal, own) {
  confirmFirst("Remove a grant", [strong("Remove"), " the grant of ", mono(principal), " on ", mono(granting), "."],
    own ? "This is your own grant: you may lose your way into this scope."
      : "What it let them do, they can no longer do.", "Remove",
    () => regrant(() => ask("/api/grant/delete", { scope: granting, principal })));
}

// a scope
function openScope() {
  if (!canChange()) return;
  $("scope-name").value = ""; fail("scope-error");
  $("scope-form").showModal();
  $("scope-name").focus();
}
async function saveScope() {
  const name = $("scope-name").value.trim();
  try {
    if (!name) throw new Error("Give it a name.");
    await ask("/api/scope/create", { name });
  } catch (error) {
    if (error instanceof Told) throw error;
    return fail("scope-error", error);
  }
  $("scope-form").close();
  await changed(name, null, `Made scope ${name}.`);
  go("scopes");
}

// ── where the keyboard is ────────────────────────────────────────────
// Tab has three stops in the page's body, one a pane. The two lists are each one thing to
// the browser; of the detail's buttons one at a time can be reached by tab, and the arrows
// move which.
const actions = () => [...$("detail").querySelectorAll("button")];
function rove(focus) {
  const all = actions();
  action = Math.max(0, Math.min(action, all.length - 1));
  all.forEach((node, index) => { node.tabIndex = index === action ? 0 : -1; });
  if (focus && all[action]) all[action].focus({ preventScroll: true });
}
function go(to) {
  if (to === "detail" && !actions().length) to = visibleSecrets().length ? "secrets" : "scopes";
  pane = to;
  if (to === "scopes") $("scopes").focus({ preventScroll: true });
  else if (to === "secrets") $("keys").focus({ preventScroll: true });
  else rove(true);
}
document.addEventListener("focusin", (event) => {
  const section = event.target.closest("main > section");
  if (!section) return;
  pane = section.dataset.pane;
  const at = actions().indexOf(event.target);
  if (pane === "detail" && at >= 0) { action = at; rove(false); }
});

function step(by) {
  const count = visibleSecrets().length;
  if (count) { secret = (secret + by + count) % count; action = 0; hide(); draw(); }
}
function stepScope(by) {
  const scopes = visibleScopes();
  if (!scopes.length) return;
  const at = scopes.findIndex((s) => s.name === scope);
  return choose(scopes[(at + by + scopes.length) % scopes.length].name);
}
function stepAction(by) {
  action = Math.max(0, Math.min(action + by, actions().length - 1));
  rove(true);
}
const down = (by) => pane === "scopes" ? stepScope(by) : pane === "secrets" ? step(by) : stepAction(by);
function ends(last) {
  if (pane === "scopes") {
    const scopes = visibleScopes();
    if (scopes.length) return choose(scopes[last ? scopes.length - 1 : 0].name);
  } else if (pane === "secrets") {
    secret = last ? Math.max(visibleSecrets().length - 1, 0) : 0; action = 0; hide(); draw();
  } else { action = last ? actions().length - 1 : 0; rove(true); }
}
const right = () => pane === "scopes" ? go(visibleSecrets().length ? "secrets" : "detail")
  : pane === "secrets" ? go("detail") : stepAction(1);
const back = () => pane === "secrets" ? go("scopes")
  : pane === "detail" ? (action === 0 ? go(visibleSecrets().length ? "secrets" : "scopes") : stepAction(-1)) : null;

const KEYS = {
  "/": () => { $("filter").focus(); $("filter").select(); }, "?": () => $("help").showModal(),
  ArrowDown: () => down(1), j: () => down(1), ArrowUp: () => down(-1), k: () => down(-1),
  ArrowRight: right, l: right, ArrowLeft: back, h: back, g: () => ends(false), G: () => ends(true),
  " ": toggle, Enter: () => pane === "scopes" ? right() : toggle(),
  c: copy, C: openCode, r: () => refresh(false), R: () => refresh(true),
  n: () => openForm(false), N: openScope, e: () => openForm(true), m: openMove, d: deleteWhat, u: undo,
  p: openGrants,
  f: () => {
    showAll = !showAll; draw();
    toast(showAll ? `Showing all ${told.scopes.length} scopes.` : "Showing only the scopes you can reach.");
  },
};
// In the filter the arrows pick while you type, enter goes to what is left, esc clears.
function filterKey(event) {
  const out = () => go(pane === "detail" || !visibleSecrets().length ? "scopes" : pane);
  if (event.key === "Escape") { $("filter").value = ""; query = ""; draw(); out(); }
  else if (event.key === "Enter") go(visibleSecrets().length ? "secrets" : "scopes");
  else if (event.key === "ArrowDown") step(1);
  else if (event.key === "ArrowUp") step(-1);
  else return;
  event.preventDefault();
}
document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || event.key === "Tab" || !token) return;
  if ($("confirm").open && event.key === "y") { event.preventDefault(); return $("confirm-yes").click(); }
  if (document.querySelector("dialog[open]")) return;
  const target = event.target;
  if (target === $("filter")) return filterKey(event);
  if (target.matches("input, select, textarea")) return;
  // space and enter belong to what has the keyboard: on a button they press that button
  if (target.matches("button") && (event.key === " " || event.key === "Enter")) return;
  if (!KEYS[event.key]) return;
  event.preventDefault();
  if (document.activeElement === document.body) go(pane);   // the keyboard is never nowhere
  carefully(KEYS[event.key])();
});
// a dialog gives the keyboard back to the pane it was opened from
document.querySelectorAll("dialog").forEach((node) => {
  // unless another dialog is open under it: then the browser gives it back to that one
  node.addEventListener("close", () => { if (!document.querySelector("dialog[open]")) go(pane); });
  node.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => node.close()));
});
$("help-open").onclick = () => $("help").showModal();
$("new-open").onclick = () => openForm(false);
$("scope-new").onclick = openScope;
$("form-save").onclick = carefully(saveForm);
$("move-save").onclick = carefully(saveMove);
$("scope-save").onclick = carefully(saveScope);
$("grant-give").onclick = carefully(giveGrant);
$("confirm-yes").onclick = carefully(async () => {
  const work = confirming;
  confirming = null;
  $("confirm").close();
  if (work) await work();
});
// enter in a field of a dialog is its save
for (const [ids, work] of [[["form-key", "form-value"], saveForm], [["move-key"], saveMove],
  [["grant-who"], giveGrant], [["scope-name"], saveScope]]) {
  for (const id of ids) {
    $(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); carefully(work)(); }
    });
  }
}
// a file: chosen with the system's own dialog, or dropped on the form
$("choose").onclick = () => $("file").click();
$("file").onchange = carefully(() => take($("file").files[0]));
$("form-value").oninput = () => { if ($("form-value").value) clearPicked(); };
$("drop").ondragover = (event) => { event.preventDefault(); $("drop").classList.add("over"); };
$("drop").ondragleave = () => $("drop").classList.remove("over");
$("drop").ondrop = carefully((event) => {
  event.preventDefault(); $("drop").classList.remove("over");
  return take(event.dataTransfer.files[0]);
});
$("filter").oninput = () => {
  query = $("filter").value.trim(); secret = 0; hide(); draw();
  carefully(async () => { await fill(scope); draw(); })();
};

carefully(enter)();
