"use strict";
// caland's page. It asks the server on this machine (never anything else), draws what it
// is told as text (never as markup), and holds a secret's value only while it is shown.

const HIDE_AFTER = 30;                 // seconds a shown value stays on the page
const LIMIT = 128 * 1024;              // the most a secret may hold, in bytes
const POLL = 400;                      // ms between looks while a workspace is loading
const STORE = "caland";                // where this tab keeps the session's token
const TOKEN_HEADER = "X-Caland-Token";
const WORKSPACE_HEADER = "X-Caland-Workspace";   // which workspace a request is about

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

// ── one thing at a time in front of the person ───────────────────────
// A key goes to the dialog that is open, and `y` to the question that is asked. So a dialog
// opens only when none is — but for a question over the grants, which is meant — and one
// that was asked for a moment ago, and comes back late, does not open over what the person
// has gone on to do.
let moment = 0;   // goes up with every key and every dialog: "has anything happened since?"
const openNow = () => [...document.querySelectorAll("dialog[open]")].map((node) => node.id);
function open(id) {
  const now = openNow();
  if (now.length && !(id === "confirm" && now.length === 1 && now[0] === "grants")) return false;
  moment += 1;
  $(id).showModal();
  return true;
}

// ── asking the server ────────────────────────────────────────────────
class Told extends Error {}
// Every request says which workspace this page believes it is in, and an answer is taken
// only if the page is still in that one when it comes: what was asked of one workspace is
// never done to another, and never shown under another's name. `anywhere` is for what is
// about no workspace: the state, the choice of one.
async function ask(path, body, anywhere = false) {
  const post = body !== undefined;
  const era = told ? told.turn : null;
  let answer;
  try {
    answer = await fetch(path, {
      method: post ? "POST" : "GET", cache: "no-store",
      headers: { [TOKEN_HEADER]: token ?? "", ...(era === null ? {} : { [WORKSPACE_HEADER]: String(era) }),
        ...(post ? { "Content-Type": "application/json" } : {}) },
      body: post ? JSON.stringify(body) : undefined,
    });
  } catch {
    trouble("caland is not running any more. Start it again from the terminal.");
    throw new Told("caland is not running");
  }
  if (answer.status === 401) { lock(); throw new Told("no key"); }
  if (answer.status === 412) { carefully(elsewhere)(); throw new Told("another workspace"); }
  const said = await answer.json().catch(() => ({}));
  if (!anywhere && era !== (told ? told.turn : null)) throw new Told("another workspace");
  if (!answer.ok) throw new Error(said.error || `caland said ${answer.status}`);
  return said;
}
// caland is in another workspace than this page shows — another tab went there. Nothing was
// done; the page lets go of what it shows and takes up the one caland is in.
async function elsewhere() {
  wipe();
  await look();
  toast("This page was showing another workspace than caland is in. Nothing was changed; it shows that one now.", true);
}
// nothing of a workspace stays on the page: no value, no name, nothing typed or chosen to
// be sent — in what is shown, in what is behind a closed dialog, in what the script holds
function wipe() {
  hide(); clearTimeout(looking);
  keys = new Map(); detail = new Map(); scope = null; secret = 0; read = null; query = "";
  picked = null; editing = null; moving = null; confirming = null; granting = null; turn += 1;
  listing = null; everyGrant = new Map(); granted = null; queue = Promise.resolve();
  for (const id of ["scopes", "secrets", "detail", "code-rows", "who", "list-rows", "list-head", "list-title",
    "list-note", "confirm-note", "confirm-title", "confirm-what", "env-scope", "move-from", "grants-scope",
    "grants-rows", "picked", "move-scope", "form-scope"]) $(id).replaceChildren();
  for (const id of ["filter", "env-file", "list-filter", "form-value", "form-key", "move-key", "grant-who",
    "scope-name", "file"]) $(id).value = "";
}
function lock() {
  token = null;
  sessionStorage.removeItem(STORE);
  for (const node of document.querySelectorAll("dialog[open]")) node.close();
  wipe();
  told = null; places = []; asked = null;
  for (const id of ["host", "picker-rows"]) $(id).replaceChildren();
  for (const id of ["picker-url", "picker-name"]) $(id).value = "";
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
  const before = told;
  const now = await ask("/api/state", undefined, true);
  if (before && before.turn !== now.turn) wipe();   // caland is in another workspace
  told = now;
  if (!before) showAll = told.show_all;
  if (told.notice && told.notice !== noticed) toast(told.notice, true);
  noticed = told.notice;
  $("host").textContent = told.workspace.host || told.workspace.name;
  $("who").textContent = told.identity ? told.identity.user : "";
  $("read-only").hidden = !told.read_only;
  document.body.dataset.readOnly = String(told.read_only);
  $("version").textContent = `caland ${told.caland}`;
  $("progress").textContent = told.phase === "connecting"
    ? "Connecting\u2026 If a sign-in opened in another tab, finish it there."
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
  if ($("list").open && listing) {   // a list that is open shows what there is now
    if (listing.grants) await allGrants();
    drawList();
  }
  document.body.dataset.phase = told.phase;   // said last: everything it stands for is drawn
  // with no workspace — none chosen yet, or the one chosen could not be reached — ask which
  if (mustChoose() && asked !== told.version && await openPicker(told.phase === "failed" ? told.error : "")) {
    asked = told.version;   // only once it is open: refused, it is asked again
  }
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
// A pane is sorted by one of its columns, up or down: the scopes by name or by how many
// secrets they hold, the secrets by key or by when they were last changed.
const sorts = { scopes: { by: 0, down: false }, secrets: { by: 0, down: false } };
const COLUMNS = {
  scopes: [["name", (s) => s.name.toLowerCase()], ["how many", (s) => s.count]],
  secrets: [["key", (row) => row[0].toLowerCase()], ["last changed", (row) => row[1] ?? 0]],
};
function sorted(rows, which) {
  const { by, down } = sorts[which], of = COLUMNS[which][by][1];
  if (by === 0 && !down) return rows;   // as the workspace gave them
  return [...rows].sort((a, b) => (of(a) < of(b) ? -1 : of(a) > of(b) ? 1 : 0) * (down ? -1 : 1));
}
const visibleScopes = () => sorted((told ? told.scopes : []).filter((s) =>
  (showAll || s.access || !s.loaded)
  && (!query || matches(s.name) || (keys.get(s.name) ?? []).some(([key]) => matches(key)))), "scopes");
const visibleSecrets = () => sorted((keys.get(scope) ?? []).filter(([key]) => !query || matches(key) || matches(scope)), "secrets");
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
  $("scopes-none").textContent = !told || told.phase === "connecting" || told.phase === "choosing" ? ""
    : query ? "Nothing matches the filter."
    : out && !showAll ? `No scopes you can reach. Press f to show all ${told.scopes.length}.`
    : told.phase === "loading" ? "" : "This workspace has no secret scopes.";

  const rows = visibleSecrets();
  secret = Math.min(secret, Math.max(rows.length - 1, 0));
  const by = sorts.scopes;
  $("scopes-title").textContent = by.by || by.down
    ? `Scopes \u00b7 by ${COLUMNS.scopes[by.by][0]} ${by.down ? "\u2193" : "\u2191"}` : "Scopes";
  for (const [id, column] of [["by-key", 0], ["by-changed", 1]]) {
    $(id).className = sorts.secrets.by === column ? `sorted${sorts.secrets.down ? " down" : ""}` : "";
  }
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
  const whole = [el("h2", { textContent: "Scope" }), el("div", { className: "acts" },
    may && !about.keyvault ? button("Import .env\u2026", "i", importEnv) : null,
    button("Copy as .env", "x", openEnv),
    may ? button("Delete scope", "D", deleteScope, "danger") : null)];
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
  if (!open("code")) return;
}

// ── changing things ──────────────────────────────────────────────────
// Everything here asks the server, which refuses what may not be changed whatever this
// page thinks. What goes wrong while a dialog is open is said in the dialog.
function fail(id, error) {
  $(id).textContent = error ? error.message : "";
  $(id).hidden = !error;
}
// One change at a time: the next is asked for when the one before has been answered and
// the workspace read again. A key pressed in between waits its turn, and finds the page
// as that change left it.
let queue = Promise.resolve();
const inTurn = (work) => (...args) => {
  const era = told ? told.turn : null;
  const next = queue.then(() => {
    // asked in one workspace, it is not done in another
    if (era !== (told ? told.turn : null)) throw new Told("another workspace");
    return work(...args);
  });
  queue = next.catch(() => {});
  return next;
};
// after a change: read the workspace again, go to what was changed — or, when it is gone,
// stay at the place it had — and say so
async function changed(toScope, toKey, saying, place = 0) {
  await look();
  if (toScope && told.scopes.some((s) => s.name === toScope)) {
    scope = toScope;
    await fill(scope);
    const at = toKey ? visibleSecrets().findIndex(([key]) => key === toKey) : -1;
    secret = at >= 0 ? at : Math.max(0, Math.min(place, visibleSecrets().length - 1));
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
let turn = 0;             // which filling-in of the form this is: an answer meant for
                          // another — a file described too late — is dropped
function clearPicked() {
  picked = null; $("file").value = "";
  $("picked").hidden = true; $("picked-note").hidden = true;
}
function openForm(edit) {
  if (!canChange()) return;
  if (edit && (!chosen() || detail.get(scope)?.keyvault)) return;
  if (!targets().length) return toast("There is no scope to put a secret in: make one with N.", true);
  editing = edit ? { scope, key: chosen()[0] } : null;
  turn += 1;
  $("form-title").textContent = edit ? "Edit secret" : "New secret";
  $("form-scope").replaceChildren(...options(targets(), scope));
  $("form-scope").disabled = $("form-key").disabled = Boolean(edit);
  $("form-key").value = edit ? editing.key : "";
  $("form-value").value = "";
  clearPicked(); fail("form-error");
  if (!open("form")) return;
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
// a file that was chosen or dropped — or text of more than one line that was pasted: say
// what it is before it goes anywhere but here
async function take(file, named = true) {
  if (!file) return;
  const mine = turn;
  fail("form-error");
  try {
    if (file.size > LIMIT) throw new Error(`${file.name} is ${size(file.size)}: a secret holds 128 kB at most.`);
    if (file.size === 0) throw new Error(`${file.name} is empty: there is nothing in it to save.`);
    const sent = base64(new Uint8Array(await file.arrayBuffer()));
    const what = await ask("/api/describe", { base64: sent });
    if (mine !== turn) return;   // the form has moved on: this answer is for one that is gone
    picked = { name: file.name, base64: sent };
    $("form-value").value = "";
    const rows = [["Size", size(what.size)], ["Kind", what.kind], ...what.facts];
    if (what.expires) rows.push(["Expires", `${what.expires.slice(0, 10)} · ${until(Date.parse(what.expires))}`]);
    $("picked").replaceChildren(el("div", { className: "name mono", textContent: file.name }), facts(rows));
    $("picked").hidden = false;
    $("picked-note").textContent = what.binary
      ? "Stored byte for byte, and comes out the same. Written nowhere on the way."
      : "Its content becomes the value, every line of it. Written nowhere on the way.";
    $("picked-note").hidden = false;
    if (named && !editing && !$("form-key").value) {
      $("form-key").value = file.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9_.@-]+/g, "-");
    }
  } catch (error) {
    if (error instanceof Told) throw error;
    if (mine !== turn) return;
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
function confirmFirst(title, what, note, label, work, danger = true) {
  $("confirm-title").textContent = title;
  $("confirm-what").replaceChildren(...what);
  $("confirm-what").className = danger ? "alert" : "quiet";
  $("confirm-yes").className = danger ? "danger" : "main";
  $("confirm-note").textContent = note;
  $("confirm-do").textContent = label;
  if (!open("confirm")) return false;
  confirming = work;
  $("confirm-no").focus();
  return true;
}
function deleteSecret() {
  const row = chosen();
  if (!canChange()) return;
  if (!row) return toast("No secret is selected. D deletes the scope.");
  if (detail.get(scope)?.keyvault) return toast(`${scope} is Azure Key Vault's: its secrets are deleted in Azure.`, true);
  const at = { scope, key: row[0] }, place = secret;
  confirmFirst("Delete secret", [strong("Delete"), " ", mono(at.key), " from ", mono(at.scope), "."],
    "u puts it back, for as long as caland runs and nothing else is deleted.", "Delete", async () => {
      const done = await ask("/api/secret/delete", at);
      await changed(at.scope, null, done.kept ? `Deleted ${at.key} — press u to put it back.`
        : `Deleted ${at.key}. Its value could not be read first, so it cannot be put back.`, place);
    });
}
// a scope has a key of its own, D: a d meant for a secret never reaches a scope
function deleteScope() {
  const row = visibleScopes().find((s) => s.name === scope);
  if (!canChange() || !row) return;
  const name = row.name, count = (keys.get(name) ?? []).length;
  const with_ = !row.loaded || !row.access ? " and whatever is in it: its secrets cannot be listed from here."
    : count ? ` and its ${count} secret${count === 1 ? "" : "s"}.` : ", which is empty.";
  confirmFirst("Delete scope", [strong("Delete"), " scope ", mono(name), with_],
    "A scope cannot be put back, and neither can what was in it.", "Delete", async () => {
      await ask("/api/scope/delete", { name });
      await changed(null, null, `Deleted scope ${name}.`);
    });
}
// the server knows what there is to put back; this page may be a change behind
async function undo() {
  if (!canChange()) return;
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
  if (!open("move")) return;
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
  if (!open("grants")) return;
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
  if (!open("scope-form")) return;
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

// ── .env: a scope's secrets as lines of text ─────────────────────────
function importEnv() {
  if (!canChange() || scope === null) return;
  if (detail.get(scope)?.keyvault) return toast(`${scope} is Azure Key Vault's: its secrets are made in Azure.`, true);
  $("env-file").value = "";
  $("env-file").click();
}
// the file is shown for what it would do before it does it: how many, and over which
async function takeEnv(file) {
  if (!file || scope === null) return;
  if (file.size > LIMIT) throw new Error(`${file.name} is ${size(file.size)}: more than can be read here.`);
  const mine = ++moment;
  const into = scope, sent = base64(new Uint8Array(await file.arrayBuffer()));
  const plan = await ask("/api/env/preview", { scope: into, base64: sent });
  $("env-file").value = "";   // the file is not kept: what was read of it is all that is used
  if (mine !== moment || openNow().length) {
    // the answer came after the person went on: it is not asked over what they are doing
    return toast(`${file.name} was not imported: something else was done meanwhile. Choose it again.`, true);
  }
  if (!plan.keys.length) return toast(`${file.name} has no KEY=value lines in it.`, true);
  const many = (n) => `${n} secret${n === 1 ? "" : "s"}`;
  const over = plan.overwrite.length;
  confirmFirst("Import .env", [strong("Put"), ` ${many(plan.keys.length)} into `, mono(into), ".",
    ...(over ? [el("p", {}, strong(`${many(over)} there will be overwritten: `), mono(plan.overwrite.join(", ")), ".")] : [])],
    (over ? "What is overwritten cannot be put back. " : "")
      + (plan.empty.length ? `Left out, having no value: ${plan.empty.join(", ")}.` : ""),
    "Import", async () => {
      const done = await ask("/api/env/import", { scope: into, base64: sent });
      await changed(into, done.done[0] ?? null,
        done.stopped_at ? null : `Imported ${many(done.done.length)} into ${into}.`);
      if (done.stopped_at) {
        toast(`Stopped at ${done.stopped_at}, after ${done.done.length} of ${done.total}: ${done.error} What went in before it stays.`, true);
      }
    }, over > 0);
}
function openEnv() {
  if (scope === null) return;
  if (!(keys.get(scope) ?? []).length) return toast("This scope has no secrets to copy.");
  $("env-scope").textContent = scope;
  if (!open("env")) return;
}
async function envKeys() {
  const names = (keys.get(scope) ?? []).map(([key]) => key);
  $("env").close();
  await put(names.map((key) => `${key}=\n`).join(""));
  toast(`Copied ${names.length} key${names.length === 1 ? "" : "s"} of ${scope} as a .env template.`);
}
function envValues() {
  const from = scope, count = (keys.get(from) ?? []).length;
  $("env").close();
  confirmFirst("Copy as .env, with values", [strong("Read"), ` all ${count} values of `, mono(from), " and put them on the clipboard."],
    "Nothing is written to disk. The clipboard can be read by other programs: clear it when you are done.",
    "Copy", async () => {
      let out = [];
      await put(ask("/api/env/export", { scope: from }).then((got) => { out = got.left_out; return got.text; }));
      toast(`Copied the values of ${from} as .env.` + (out.length ? ` Left out, not being text: ${out.join(", ")}.` : ""));
    });
}

// ── lists to look through and pick from ──────────────────────────────
// The stale report, the overview and who-has-access are one dialog: a heading, rows, and
// what a key does. Arrows move, enter goes to what is picked, esc closes.
let listing = null;   // { rows: [{ cells, go }], at, keys: { letter: work }, again }
function openList(make) {
  listing = { make, at: 0, rows: [], keys: {} };
  $("list-filter").value = "";
  drawList();
  if (!open("list")) return;
  (listing.filter ? $("list-filter") : $("list-box")).focus();
}
function drawList() {
  const made = listing.make($("list-filter").value.trim());
  Object.assign(listing, made, { at: Math.min(listing.at, Math.max(made.rows.length - 1, 0)) });
  $("list-title").textContent = made.title;
  $("list-note").textContent = made.note ?? "";
  $("list-filter").hidden = !made.filter;
  $("list-filter").placeholder = made.filter ?? "";
  $("list-head").replaceChildren(el("tr", {}, ...made.head.map((text) => el("th", { textContent: text }))));
  $("list-rows").replaceChildren(...made.rows.map((row, index) => {
    const node = el("tr", {}, ...row.cells.map((cell) => el("td", {}, cell)));
    node.setAttribute("aria-selected", String(index === listing.at));
    node.onclick = () => { listing.at = index; pickList(); };
    return node;
  }));
  $("list-none").hidden = made.rows.length > 0;
  $("list-none").textContent = made.none ?? "Nothing.";
  $("list-rows").querySelector("[aria-selected=true]")?.scrollIntoView({ block: "nearest" });
}
function pickList() {
  const row = listing.rows[listing.at];
  if (!row) return;
  $("list").close();
  return row.go();
}
function listKey(event) {
  const typing = event.target === $("list-filter");
  const move = { ArrowDown: 1, ArrowUp: -1, ...(typing ? {} : { j: 1, k: -1 }) }[event.key];
  if (move) {
    const count = listing.rows.length;
    if (count) listing.at = (listing.at + move + count) % count;
    drawList();
  } else if (event.key === "Enter") carefully(pickList)();
  else if (!typing && listing.keys[event.key]) carefully(listing.keys[event.key])();
  else return;
  event.preventDefault();
}
// go to a scope, and to a secret in it when one is named
async function goTo(toScope, toKey) {
  if (query) { $("filter").value = ""; query = ""; }
  if (!visibleScopes().some((s) => s.name === toScope)) showAll = true;
  await choose(toScope);
  const at = toKey ? visibleSecrets().findIndex(([key]) => key === toKey) : -1;
  if (at >= 0) { secret = at; draw(); }
  go(at >= 0 ? "secrets" : "scopes");
}

// a list asked for while the workspace is still being read says so, and is written again
// as more of it arrives
const reading = () => told.phase === "ready" ? "" : "The workspace is still being read: this is what there is so far. ";
// secrets that nobody has changed for a while, oldest first
const STALE = [30, 90, 180, 365];
function openStale() {
  if (!told) return;
  openList(() => {
    const days = told.stale_after, before = Date.now() - days * 864e5;
    const old = [...keys].flatMap(([name, rows]) => rows.filter(([, ms]) => ms && ms < before)
      .map(([key, ms]) => ({ scope: name, key, ms }))).sort((a, b) => a.ms - b.ms);
    return {
      title: `Not changed in ${days} days: ${old.length} secret${old.length === 1 ? "" : "s"}`,
      note: reading() + "t: another number of days · c: copy as Markdown · enter: go to it. No value is read for this.",
      head: ["Scope", "Key", "Last changed", "Age"],
      none: told.phase === "ready" ? `Every secret here was changed in the last ${days} days.` : "Nothing so far.",
      rows: old.map((row) => ({ cells: [mono(row.scope), mono(row.key), day(row.ms), age(row.ms)],
        go: () => goTo(row.scope, row.key) })),
      keys: {
        t: async () => {
          told.stale_after = STALE[(STALE.indexOf(days) + 1) % STALE.length];
          drawList();
          await ask("/api/settings", { stale_after: told.stale_after });
        },
        c: async () => {
          const name = (text) => "`" + text.replace(/[\r\n]+/g, " ").replace(/\|/g, "\\|").replace(/`/g, "'") + "`";
          const lines = ["| Scope | Key | Last changed | Age |", "|---|---|---|---|",
            ...old.map((row) => `| ${name(row.scope)} | ${name(row.key)} | ${day(row.ms)} | ${age(row.ms)} |`)];
          await put(lines.join("\n"));
          $("list-note").textContent = `Copied ${old.length} row${old.length === 1 ? "" : "s"} as Markdown.`;
        },
      },
    };
  });
}

// every scope's grants, asked for once per reading of the workspace
let everyGrant = new Map(), granted = null;
async function allGrants() {
  if (granted !== told.version) {
    everyGrant = new Map(Object.entries((await ask("/api/grants")).scopes));
    granted = told.version;
  }
  return everyGrant;
}
const RANK = { MANAGE: 3, WRITE: 2, READ: 1 };
// what you can reach: every scope, your access, and how many have a grant on it
async function openOverview() {
  if (!told) return;
  const mine = ++moment;
  await allGrants();
  if (mine !== moment) return;
  openList(() => {
    const grants = everyGrant;
    const rows = [...told.scopes].sort((a, b) => (RANK[b.access] ?? 0) - (RANK[a.access] ?? 0) || a.name.localeCompare(b.name));
    return {
      title: `What you can reach: ${rows.filter((s) => s.access).length} of ${rows.length} scopes`,
      note: reading() + "enter: go to the scope.",
      grants: true,
      head: ["Scope", "Your access", "With a grant"],
      rows: rows.map((s) => ({ cells: [mono(s.name), pill(s.access), String((grants.get(s.name) ?? []).length)],
        go: () => goTo(s.name) })),
    };
  });
}
// what somebody else can: every grant made to a name, strongest first
async function openWho() {
  if (!told) return;
  const mine = ++moment;
  await allGrants();
  if (mine !== moment) return;
  openList((typed) => {
    const all = [...everyGrant].flatMap(([name, rows]) => rows.map(([who, may]) => ({ who, scope: name, may })))
      .sort((a, b) => a.who.localeCompare(b.who) || (RANK[b.may] ?? 0) - (RANK[a.may] ?? 0) || a.scope.localeCompare(b.scope));
    const letters = typed.toLowerCase();
    const fits = (text) => { let at = 0; for (const c of letters) { at = text.toLowerCase().indexOf(c, at) + 1; if (!at) return false; } return true; };
    const rows = all.filter((row) => fits(row.who));
    return {
      title: "Who has access",
      filter: "a user, a group or a service principal",
      grants: true,
      note: reading() + "Grants made to the name itself. What somebody reaches through a group is under the group's name.",
      head: ["Principal", "Scope", "May"],
      none: all.length ? "Nobody of that name has a grant." : "No grants could be listed: that takes MANAGE on a scope.",
      rows: rows.map((row) => ({ cells: [row.who, mono(row.scope), pill(row.may)], go: () => goTo(row.scope) })),
    };
  });
}

// sort the pane the keyboard is in by its next column, or the other way round
function sortBy(which, by, down) {
  const kept = which === "secrets" ? (chosen() ?? [])[0] : null;
  Object.assign(sorts[which], { by, down });
  if (kept !== null) secret = Math.max(0, visibleSecrets().findIndex(([key]) => key === kept));
  hide(); draw();
}
const sortNext = () => { const which = pane === "scopes" ? "scopes" : "secrets"; sortBy(which, (sorts[which].by + 1) % 2, false); };
const sortOver = () => { const which = pane === "scopes" ? "scopes" : "secrets"; sortBy(which, sorts[which].by, !sorts[which].down); };

// ── which workspace ──────────────────────────────────────────────────
let places = [], place = 0;   // the workspaces there are to choose from, and the one picked
let asked = null;             // the version of the state the picker was last opened for
let noticed = "";             // what the server had to say, once it was said
let going = false;            // on the way to a workspace: asked once, not twice
const mustChoose = () => !told || told.phase === "choosing" || (told.phase === "failed" && !told.identity);
async function openPicker(why = "") {
  const mine = ++moment;
  const got = await ask("/api/workspaces", undefined, true);
  if (mine !== moment && !mustChoose()) return false;
  places = got.workspaces;
  place = Math.max(0, places.findIndex((w) => got.current ? w.name === got.current : w.default));
  for (const id of ["picker-url", "picker-name"]) $(id).value = "";
  $("picker-save").checked = false; $("picker-keep").hidden = true;
  $("picker-close").hidden = mustChoose();   // with no workspace there is nothing to go back to
  fail("picker-error", why ? new Error(why) : null);
  drawPicker();
  if (!open("picker")) return false;
  (places.length ? $("picker-box") : $("picker-url")).focus();
  return true;
}
function drawPicker() {
  $("picker-rows").replaceChildren(...places.map((w, index) => {
    const row = el("tr", {}, el("td", { className: "mono", textContent: w.name }),
      el("td", { className: "mono", textContent: w.host }), el("td", { className: "dim", textContent: w.from }));
    row.setAttribute("aria-selected", String(index === place));
    row.onclick = carefully(() => { place = index; return goToWorkspace({ name: w.name, host: w.host }); });
    return row;
  }));
  $("picker-none").hidden = places.length > 0;
  $("picker-rows").querySelector("[aria-selected=true]")?.scrollIntoView({ block: "nearest" });
}
async function goToWorkspace(body) {
  if (going) return;   // enter twice is one sign-in
  going = true;
  try {
    await ask("/api/connect", body, true);
  } catch (error) {
    if (error instanceof Told) throw error;
    return fail("picker-error", error);
  } finally {
    going = false;
  }
  told.phase = "connecting";   // it is on its way: the choice need not come back
  $("picker").close();
  wipe();   // nothing of the workspace that is left stays on the page
  await look();
  go("scopes");
}
function signIn() {
  const url = $("picker-url").value.trim();
  if (!url) return fail("picker-error", new Error("Type the workspace's address, or pick one from the list."));
  const keep = $("picker-save").checked, name = $("picker-name").value.trim();
  if (keep && !name) return fail("picker-error", new Error("Give the profile a name, or do not keep it."));
  return goToWorkspace(keep ? { url, save_as: name } : { url });
}
function pickerKey(event) {
  if (event.target.matches("input[type=text]")) {
    if (event.key === "Enter") { event.preventDefault(); carefully(signIn)(); }
    return;
  }
  const move = { ArrowDown: 1, ArrowUp: -1, j: 1, k: -1 }[event.key];
  if (move && places.length) { place = (place + move + places.length) % places.length; drawPicker(); }
  else if (event.key === "Enter" && places[place] && !event.target.matches("button, input")) {
    carefully(goToWorkspace)({ name: places[place].name, host: places[place].host });
  } else return;
  event.preventDefault();
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
  "/": () => { $("filter").focus(); $("filter").select(); }, "?": () => open("help"),
  ArrowDown: () => down(1), j: () => down(1), ArrowUp: () => down(-1), k: () => down(-1),
  ArrowRight: right, l: right, ArrowLeft: back, h: back, g: () => ends(false), G: () => ends(true),
  " ": toggle, Enter: () => pane === "scopes" ? right() : toggle(),
  c: copy, C: openCode, r: () => refresh(false), R: () => refresh(true),
  n: () => openForm(false), N: openScope, e: () => openForm(true), m: openMove,
  d: deleteSecret, D: deleteScope, u: inTurn(undo),
  p: openGrants, P: openWho, a: openOverview, A: openStale, i: importEnv, x: openEnv,
  s: sortNext, S: sortOver, w: () => openPicker(),
  f: async () => {
    showAll = !showAll; draw();
    toast(showAll ? `Showing all ${told.scopes.length} scopes.` : "Showing only the scopes you can reach.");
    await ask("/api/settings", { show_all: showAll });   // kept for the next time
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
  moment += 1;
  if ($("confirm").open && event.key === "y") { event.preventDefault(); return $("confirm-yes").click(); }
  if ($("env").open && (event.key === "1" || event.key === "2")) {
    event.preventDefault();
    return $(event.key === "1" ? "env-keys" : "env-values").click();
  }
  if ($("list").open && !$("confirm").open) return listKey(event);
  if ($("picker").open) return pickerKey(event);
  if (document.querySelector("dialog[open]")) return;
  const target = event.target;
  if (target === $("filter")) return filterKey(event);
  if (target.matches("input, select, textarea")) return;
  // space and enter belong to what has the keyboard: on a button they press that button
  if (target.matches("button") && (event.key === " " || event.key === "Enter")) return;
  if (!KEYS[event.key]) return;
  // with no workspace — none chosen, or on the way to one — a key has nothing to act on,
  // but the keys' own list and the choice of a workspace
  if ((!told || !told.identity) && !["?", "w"].includes(event.key)) return;
  event.preventDefault();
  if (document.activeElement === document.body) go(pane);   // the keyboard is never nowhere
  carefully(KEYS[event.key])();
});
// a dialog gives the keyboard back to the pane it was opened from
document.querySelectorAll("dialog").forEach((node) => {
  // unless another dialog is open under it: then the browser gives it back to that one
  node.addEventListener("close", () => {
    if (document.querySelector("dialog[open]")) return;
    // with no workspace, what is left to do is choose one: whatever was open, it is asked
    if (token && told && mustChoose()) carefully(openPicker)(told.phase === "failed" ? told.error : "");
    else go(pane);
  });
  node.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => node.close()));
});
$("help-open").onclick = () => open("help");
$("new-open").onclick = () => openForm(false);
$("picker-go").onclick = carefully(signIn);
// said here and not in the page: the page itself names no address at all, so that it can
// be seen at a glance to load nothing from one
$("picker-url").placeholder = "https://adb-1234567890123456.7.azuredatabricks.net";
$("picker-save").onchange = () => {
  $("picker-keep").hidden = !$("picker-save").checked;
  if ($("picker-save").checked) $("picker-name").focus();
};
// With no workspace to go back to, esc does not close the choice of one — and where a
// browser closes it all the same (it lets a page hold esc back only so often), it is asked
// again.
$("picker").addEventListener("cancel", (event) => { if (mustChoose()) event.preventDefault(); });

$("env-file").onchange = carefully(() => takeEnv($("env-file").files[0]));
$("env-keys").onclick = carefully(envKeys);
$("env-values").onclick = envValues;
$("list-filter").oninput = () => { listing.at = 0; drawList(); };
$("by-key").onclick = () => sortBy("secrets", 0, sorts.secrets.by === 0 && !sorts.secrets.down);
$("by-changed").onclick = () => sortBy("secrets", 1, sorts.secrets.by === 1 && !sorts.secrets.down);
$("forget").onclick = carefully(async () => {
  await ask("/api/forget", {});
  hide(); $("help").close(); draw();
  toast("Forgot every value caland held. What could be put back is forgotten with it.");
});
$("scope-new").onclick = openScope;
$("form-save").onclick = carefully(inTurn(saveForm));
$("move-save").onclick = carefully(inTurn(saveMove));
$("scope-save").onclick = carefully(inTurn(saveScope));
$("grant-give").onclick = carefully(inTurn(giveGrant));
$("confirm-yes").onclick = () => {
  const work = confirming;
  confirming = null;
  $("confirm").close();
  if (work) carefully(inTurn(work))();
};
// enter in a field of a dialog is its save
for (const [ids, work] of [[["form-key", "form-value"], saveForm], [["move-key"], saveMove],
  [["grant-who"], giveGrant], [["scope-name"], saveScope]]) {
  for (const id of ids) {
    $(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); carefully(inTurn(work))(); }
    });
  }
}
// a question that is cancelled is forgotten, with whatever it was holding to do
$("confirm").addEventListener("cancel", () => { confirming = null; });
$("confirm-no").addEventListener("click", () => { confirming = null; });
// a form that is closed keeps nothing that was typed into it or chosen for it
const formGone = () => { turn += 1; $("form-value").value = ""; clearPicked(); };
// esc says so at once. That a dialog is closed is said a moment after it is — and by then
// the form may be open again, with something typed into it that is not to be cleared.
$("form").addEventListener("cancel", formGone);
$("form").addEventListener("close", () => { if (!$("form").open) formGone(); });
// A field holds one line, and joins what is pasted into it to one: a certificate pasted
// there would be saved broken. More than one line is taken as it is, like a file.
$("form-value").addEventListener("paste", (event) => {
  const text = event.clipboardData?.getData("text") ?? "";
  if (!/[\r\n]/.test(text)) return;
  event.preventDefault();
  carefully(() => take(new File([text], "pasted text", { type: "text/plain" }), false))();
});
// a file: chosen with the system's own dialog, or dropped on the form
$("choose").onclick = () => $("file").click();
$("file").onchange = carefully(() => take($("file").files[0]));
$("form-value").oninput = () => { if ($("form-value").value) { turn += 1; clearPicked(); } };
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
