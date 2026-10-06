"use strict";
// caland's page. It asks the server on this machine (never anything else), draws what it
// is told as text (never as markup), and holds a secret's value only while it is shown.

const HIDE_AFTER = 30;                 // seconds a shown value stays on the page
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
let told = null;          // the server's state: phase, who, the scopes
let keys = {};            // scope -> [[key, changed in ms], ...]
let detail = {};          // scope -> { access, keyvault, grants }
let scope = null;         // the selected scope's name
let secret = 0;           // the selected secret's place among those shown
let shown = null;         // { scope, key, value } while a value is on the page
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
  hide();
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
  token = token ?? sessionStorage.getItem(STORE);
  if (!token) return lock();
  $("app").hidden = false;
  await look();
  go("scopes");
}

// ── keeping up with the workspace ────────────────────────────────────
let looking = null;
async function look() {
  clearTimeout(looking);
  const first = told === null;
  told = await ask("/api/state");
  if (first) showAll = told.show_all;
  $("host").textContent = told.workspace.host || told.workspace.name;
  $("who").textContent = told.identity ? told.identity.user : "";
  $("read-only").hidden = !told.read_only;
  $("version").textContent = `caland ${told.caland}`;
  $("progress").textContent = told.phase === "connecting" ? "Connecting…"
    : told.phase === "loading" ? `Loading scopes… ${told.done}/${told.total}` : "";
  trouble(told.phase === "failed" ? told.error || "The workspace could not be read." : "");

  const names = new Set(told.scopes.map((s) => s.name));
  for (const name of Object.keys(keys)) if (!names.has(name)) { delete keys[name]; delete detail[name]; }
  if (told.phase === "ready" && read !== told.version) {
    // everything has been read: take every name at once, so that filtering never asks
    keys = (await ask("/api/keys")).scopes;
    detail = {};
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
  if (!row || !row.loaded || detail[name]) return;
  const said = await ask(`/api/scope?name=${encodeURIComponent(name)}`);
  keys[name] = said.secrets;
  detail[name] = { access: said.access, keyvault: said.keyvault, grants: said.grants };
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
  && (!query || matches(s.name) || (keys[s.name] ?? []).some(([key]) => matches(key))));
const visibleSecrets = () => (keys[scope] ?? []).filter(([key]) => !query || matches(key) || matches(scope));
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
function button(label, key, work) {
  const node = el("button", {}, label, " ", el("kbd", { textContent: key }));
  node.onclick = carefully(work);
  return node;
}

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
    : (keys[scope] ?? []).length ? "Nothing here matches the filter."
    : row && !row.access ? "You have no access to this scope." : "No secrets in this scope.";
  for (const list of [$("scopes"), $("secrets")]) {
    list.querySelector("[aria-selected=true]")?.scrollIntoView({ block: "nearest" });
  }
  drawDetail(rows[secret]);
  rove(had);
}

function drawDetail(row) {
  const about = detail[scope];
  if (scope === null || !about) return $("detail").replaceChildren();
  const you = told.identity ? told.identity.user : "";
  const backed = about.keyvault ? "Azure Key Vault" : "Databricks";
  const access = [el("h2", { textContent: "Who has access" }),
    about.grants.length
      ? el("table", {}, el("tbody", {}, ...about.grants.map(([who, permission]) =>
          el("tr", {}, el("td", { textContent: who === you ? `${who} (you)` : who }), el("td", {}, pill(permission))))))
      : el("p", { className: "none", textContent: "No grants are listed. Listing them takes MANAGE on the scope." }),
    el("p", { className: "meta", textContent: "Grants are for a whole scope: whoever may read one secret in it may read them all." })];
  if (!row) {
    return $("detail").replaceChildren(el("h2", { textContent: "Scope" }),
      el("div", { className: "name mono", textContent: scope }),
      facts([["Backed by", backed], ["Your access", pill(about.access)]]), ...access);
  }
  const [key, changed] = row;
  const open = shown && shown.scope === scope && shown.key === key;
  const value = el("pre", { className: `value mono${open ? " shown" : ""}`,
    textContent: open ? shown.value : "•".repeat(16) });
  const hint = el("div", { className: "meta", id: "hint",
    textContent: open ? `hides in ${left} s` : "read from the workspace when you ask, never before" });
  $("detail").replaceChildren(el("h2", { textContent: "Secret" }),
    el("div", { className: "name mono", textContent: key }),
    facts([["Scope", el("span", { className: "mono", textContent: scope })], ["Backed by", backed],
      ["Your access", pill(about.access)],
      ["Last changed", changed ? `${day(changed)} · ${age(changed)}${age(changed) === "today" ? "" : " ago"}` : "—"]]),
    el("h2", { textContent: "Value" }), value, hint,
    el("div", { className: "acts" }, button(open ? "Hide" : "Show", "space", toggle), button("Copy", "c", copy),
      button("Copy as code", "C", openCode)),
    ...access);
}

async function choose(name) {
  scope = name; secret = 0; action = 0; hide();
  draw();
  await fill(name);
  if (scope === name) draw();
}

// ── a value: shown when asked, gone when hidden ──────────────────────
const value = (row) => ask("/api/value", { scope, key: row[0] }).then((said) => said.value);
async function toggle() {
  const row = chosen();
  if (!row) return;
  if (shown && shown.scope === scope && shown.key === row[0]) { hide(); return draw(); }
  const at = { scope, key: row[0] };
  const text = await value(row);
  if (scope !== at.scope || (chosen() ?? [])[0] !== at.key) return;   // moved on while it came
  shown = { ...at, value: text };
  left = HIDE_AFTER;
  clearInterval(timer);
  timer = setInterval(() => {
    left -= 1;
    if (left <= 0) { hide(); draw(); } else if ($("hint")) $("hint").textContent = `hides in ${left} s`;
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
  await put(value(row));
  toast(`Copied ${row[0]}.`);
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
  const forms = [["Python (dbutils)", `dbutils.secrets.get(scope="${scope}", key="${row[0]}")`],
    ["Spark conf or a job", `{{secrets/${scope}/${row[0]}}}`],
    ["Databricks CLI", `databricks secrets get-secret ${scope} ${row[0]}`]];
  $("code-rows").replaceChildren(...forms.map(([label, code]) => {
    const node = el("button", {}, el("span", { textContent: label }), el("span", { className: "mono", textContent: code }));
    node.onclick = carefully(async () => { await put(code); $("code").close(); toast(`Copied: ${code}`); });
    return node;
  }));
  $("code").showModal();
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
  node.addEventListener("close", () => go(pane));
  node.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => node.close()));
});
$("help-open").onclick = () => $("help").showModal();
$("filter").oninput = () => {
  query = $("filter").value.trim(); secret = 0; hide(); draw();
  carefully(async () => { await fill(scope); draw(); })();
};

carefully(enter)();
