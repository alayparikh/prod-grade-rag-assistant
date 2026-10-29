// Page wiring for the demo. Nothing here searches or queries by itself:
//   search.js does document search, orders.js turns order questions into SQL,
//   scene.js draws the 3D hero. This file connects them to the page:
//   - the scroll story (scroll position -> scene pose and captions)
//   - roles ("Search as"), shared by the document and order sections
//   - the five failure cases, whose explanations are computed from each run
//   - rendering results, the X-ray panels and the privacy meter
//   - startup: index, models, sql.js and orders.db all load before the
//     privacy meter starts counting, so searching adds zero requests.
import { Engine, tokenize } from "./search.js";
import { INTENTS, Translator, applyRole, loadContext, run, summarize } from "./orders.js";

const SQLJS = "https://cdn.jsdelivr.net/npm/sql.js@1.15.2/dist/";

const EXAMPLES = [
  "What is the production deploy window?",
  "Who works on observability?",
  "What is Sam Rivera's LinkedIn?",
  "How long are database backups kept?",
  "How often does the load balancer run health checks?",
  "What happens to a flaky test?",
  "What is the capital of Portugal?",
];

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (s) => document.querySelector(s);

// ---- scroll story ------------------------------------------------------
const story = $(".story");
const heroCopy = $(".hero-copy");
const steps = [...document.querySelectorAll(".step")];
let scene = null;

function onScroll() {
  const rect = story.getBoundingClientRect();
  const span = rect.height - innerHeight;
  // 0 at the top of the story, 3 at its end: one unit per pipeline step.
  const p = Math.max(0, Math.min(1, -rect.top / span)) * 3.4;
  scene?.setProgress(p);
  heroCopy.style.opacity = String(Math.max(0, 1 - p * 2.5));
  steps.forEach((el) => {
    const at = Number(el.dataset.at);
    el.classList.toggle("on", p > at - 0.55 && (at === 3 || p < at + 0.45));
  });
}
addEventListener("scroll", onScroll, { passive: true });

import("./scene.js")
  .then(({ mountScene }) => mountScene($(".stage canvas"), { reducedMotion }))
  .then((s) => { scene = s; onScroll(); })
  .catch(() => document.body.classList.add("no-webgl"));

// ---- search ------------------------------------------------------------
const status = $(".status");
const form = $("#ask");
const input = $("#q");
const button = form.querySelector("button");
const results = $("#results");
let engine = null;
let ready = null;       // resolves once both models have loaded
let lastQuestion = null;

const escape = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const short = (source) => source.replace(/\.[a-z]+$/, "");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

function setStatus(text, fraction) {
  status.innerHTML = escape(text) + (fraction == null ? "" :
    `<span class="meter" aria-hidden="true"><i style="width:${Math.round(fraction * 100)}%"></i></span>`);
}

// Mark the question's words inside a passage, matching the keyword search's
// own idea of a word. Filler words are left unmarked: highlighting every
// "are" and "the" hides the words that actually matched.
const FILLER = new Set("the and are was were what who how does did for with from that this have has its into when where which why you your about".split(" "));
function highlight(text, question) {
  const terms = new Set(tokenize(question).filter((t) => t.length > 2 && !FILLER.has(t)));
  return escape(text).replace(/[\p{L}\p{N}]+/gu, (w) => terms.has(w.toLowerCase()) ? `<mark>${w}</mark>` : w);
}

// ---- who is searching ----------------------------------------------------
// Folder permissions as the real app would read them from the NAS. Applied
// before retrieval: a file outside a role can't be ranked, scored or quoted.
const isResume = (f) => /_resume\./.test(f);
const ROLES = [
  { id: "admin", label: "Admin", can: () => true },
  { id: "engineer", label: "Engineer", can: (f) => !isResume(f) },
  { id: "hr", label: "HR", can: (f) => isResume(f) || ["team_roster.md", "company_handbook.md", "onboarding_guide.md", "security_policy.md"].includes(f) },
  // Contractors staff the West warehouse: the order and shipping docs, not HR or engineering.
  { id: "contractor", label: "Contractor", can: (f) => ["company_handbook.md", "onboarding_guide.md", "testing_standards.md",
    "order_lifecycle.md", "shipping_policy.md", "product_catalog.md"].includes(f) },
];
let role = ROLES[0];
const allowed = () => new Set(engine.files.filter(role.can));

// One role, shown in both sections.
const segs = [...document.querySelectorAll(".roles .seg")];
segs.forEach((seg, n) => {
  for (const r of ROLES) {
    seg.insertAdjacentHTML("beforeend",
      `<label><input type="radio" name="role-${n}" value="${r.id}" ${r === role ? "checked" : ""}><span>${r.label}</span></label>`);
  }
});
function showAccess() {
  if (!engine) return;
  const open = allowed().size, hidden = engine.files.length - open;
  const el = $("#try .access");
  el.textContent = hidden ? `Can open ${open} of ${engine.files.length} files · ${hidden} hidden from this role`
                          : `Can open all ${open} files`;
  el.classList.toggle("blocked", hidden > 0);
  const scope = { admin: "Sees every order", engineer: "Sees every order · emails and prices hidden",
    hr: "No access to order data", contractor: "West-region orders only · emails and prices hidden" }[role.id];
  const oel = $("#orders .access");
  oel.textContent = scope;
  oel.classList.toggle("blocked", role.id !== "admin");
}
function setRole(id) {
  role = ROLES.find((r) => r.id === id);
  segs.forEach((seg) => { seg.querySelector(`input[value="${id}"]`).checked = true; });
  showAccess();
}
segs.forEach((seg) => seg.addEventListener("change", (e) => {
  setRole(e.target.value);
  // Same questions, new permissions.
  if (lastQuestion) ask(lastQuestion);
  if (lastOrderQuestion) askOrders(lastOrderQuestion);
}));

// ---- the four failure cases ------------------------------------------------
// Each explanation is worked out from what the search actually returned, so
// the page cannot claim something the run didn't show.
const rankOf = (ids, source, chunks) => {
  const i = ids.findIndex((id) => chunks[id].source === source);
  return i < 0 ? null : i + 1;
};
const CASES = [
  {
    title: "It uses different words",
    body: "People ask the way they'd say it. Documents say it the way the author wrote it.",
    question: "What time are we allowed to push to production?",
    explain(r, c) {
      const want = "company_handbook.md";
      const kw = rankOf(r.keyword, want, c), vec = rankOf(r.vector, want, c);
      const top = r.passages[0]?.chunk.source;
      return [
        "The handbook never says “push”. It says “deploy window”.",
        `Exact-word search ranked ${escape(short(c[r.keyword[0]].source))} first${kw ? ` and the handbook #${kw}` : " and missed the handbook"}. ` +
        `Meaning search ranked the handbook ${vec ? `#${vec}` : "outside its top results"}. ` +
        (top ? `The answer came from ${escape(top)}.` : "Nothing cleared the cutoff."),
      ];
    },
  },
  {
    title: "The answer is inside formatting",
    body: "Links, tables and headings vanish when files are flattened to plain text.",
    question: "What is Sam Rivera's LinkedIn?",
    explain(r) {
      const url = r.passages.map((p) => p.chunk.text).join(" ").match(/https?:\/\/[^\s)]*linkedin[^\s)]*/i)?.[0];
      return [
        "In the Word file, the address exists only behind the link text “LinkedIn”.",
        url ? `Plain-text extraction keeps the word and loses the address. This pipeline reads the document's link table, so it found ${escape(url)}.`
            : "This run did not surface the address.",
      ];
    },
  },
  {
    title: "It answers anyway",
    body: "Most assistants answer from whatever they found, even when nothing fits.",
    question: "What is our parental leave policy?",
    explain(r, c) {
      const best = r.ranked[0]?.score;
      return r.passages.length ? ["A passage cleared the cutoff for this question."] : [
        `Similarity search always returns something. Here its top pick was ${escape(short(c[r.vector[0]].source))}, and an assistant that answers from whatever it retrieves would have answered from that.`,
        `The reranker scored the best passage ${best.toFixed(1)}, under the ${engine.config.min_score} cutoff, so the page says the documents don't cover it.`,
      ];
    },
  },
  {
    title: "It shows people what they shouldn't see",
    body: "Search that ignores file permissions turns every document into a company-wide one.",
    question: "What is Jane Doe's email?",
    role: "contractor",
    explain(r) {
      return [
        `As a Contractor you can open ${allowed().size} of ${engine.files.length} files, and resumes aren't among them, so they were removed before searching.`,
        r.passages.length ? "The passages shown come only from files a Contractor can open."
          : "You get the same message as for something that doesn't exist, so nobody learns the file is there. Switch to Admin above to see the difference.",
      ];
    },
  },
  {
    title: "It can't read the database",
    body: "The answer to “where is my order” is a row in a database, not a sentence in a document.",
    question: "Why is order 1042 late?",
    kind: "orders",
    explain(o) {
      const docs = o.docsOnly;
      const top = docs?.passages[0];
      const row = o.row ?? {};
      return [
        `Document search alone ${top ? `returned ${escape(short(top.chunk.source))}, which never mentions order 1042`
          : "found nothing about order 1042"}: no document can know an order's status.`,
        row.status ? `The status is a row in the orders table: ${escape(row.status)}${row.hold_reason ? `, held for ${escape(row.hold_reason)}` : ""}, promised by ${escape(row.promised_by)}. ` +
          `${o.why ? `Why that hold happens, and how it's cleared, comes from ${escape(o.why.chunk.source)}, shown beside it.` : ""}`
          : "This role can't see that order, so the query returned nothing.",
      ];
    },
  },
];

const cases = $(".cases");
CASES.forEach((k, i) => {
  const el = document.createElement("article");
  el.className = "case";
  el.innerHTML = `<h3>${k.title}</h3><p>${k.body}</p>
    ${k.role ? `<span class="as">Runs as ${ROLES.find((r) => r.id === k.role).label}</span>` : ""}
    <q>${escape(k.question)}</q><button type="button">Run it</button>`;
  el.querySelector("button").addEventListener("click", () => {
    el.classList.add("ran");
    setRole(k.role ?? "admin");
    const orders = k.kind === "orders";
    (orders ? oinput : input).value = k.question;
    $(orders ? "#orders" : "#try").scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
    orders ? askOrders(k.question, k) : ask(k.question, k);
  });
  cases.append(el);
});

// ---- rendering -------------------------------------------------------------
function chip(id, i, r, extra = "") {
  const c = engine.chunks[id];
  const tail = c.section ? c.section.split(" > ").pop() : "";
  const answer = r.passages.some((p) => p.id === id);
  return `<li class="chip${answer ? " answer" : ""}${extra}" data-id="${id}" tabindex="0"
    title="${escape(c.source)}${tail ? " · " + escape(tail) : ""}"><i>${i + 1}</i><span>${escape(short(c.source))}${tail ? " · " + escape(tail) : ""}</span></li>`;
}

function xray(r) {
  const min = engine.config.min_score;
  const lane = (title, kind, ids, f = (id, i) => chip(id, i, r)) => `<div class="lane ${kind}"><h4>${title}</h4>${
    ids.length ? `<ol>${ids.map(f).join("")}</ol>` : `<p class="empty-lane">no matching words</p>`}</div>`;
  return `<details class="xray" open><summary>Pipeline X-ray<small>hover a passage to follow it</small></summary>
    <div class="lanes">
      ${lane("Meaning search", "meaning", r.vector)}
      ${lane("Exact-word search", "keyword", r.keyword)}
      ${lane("Merged by rank", "merged", r.fused)}
      ${lane(`Reranked · cutoff ${min}`, "ranked", r.ranked.map((x) => x.id), (id, i) => {
        const s = r.ranked[i].score;
        return chip(id, i, r, s < min ? " dropped" : "").replace("</li>", `<em>${s.toFixed(1)}</em></li>`);
      })}
    </div></details>`;
}

function render(question, r, k) {
  const cfg = engine.config;
  const ms = (x) => `${Math.round(x)} ms`;
  const explain = k ? `<div class="explain"><b>What just happened</b>${k.explain(r, engine.chunks).map((t) => `<p>${t}</p>`).join("")}</div>` : "";
  const readout = `<p class="readout">searched as <strong>${role.label}</strong>
    · <span class="dot meaning"></span>meaning <strong>${r.vector.length}</strong>
    · <span class="dot keyword"></span>exact words <strong>${r.keyword.length}</strong>
    · <span class="dot answer"></span>answers <strong>${r.passages.length}</strong>
    · total <strong>${ms(r.timings.total)}</strong></p>`;

  let body;
  if (!r.passages.length) {
    const best = r.ranked[0]?.score;
    body = `<div class="empty"><h3>The documents don't cover this</h3>
      <p>${best == null ? "No passage matched." : `The closest passage scored ${best.toFixed(1)}; a passage needs ${cfg.min_score} or higher to count as an answer.`}</p></div>`;
  } else {
    // Scores are logits; the bar shows where each sits between the cutoff
    // and a confident match (about +6) for this reranker.
    const width = (s) => `${Math.round(Math.max(0, Math.min(1, (s - cfg.min_score) / (6 - cfg.min_score))) * 100)}%`;
    body = r.passages.map((p, i) => `
      <article class="result">
        <div class="rank" aria-label="Rank ${i + 1}">${i + 1}</div>
        <div>
          <div class="meta">
            <span class="file">${escape(p.chunk.source)}</span>
            ${p.chunk.section ? `<span>${escape(p.chunk.section)}</span>` : ""}
            <span class="score">score ${p.score.toFixed(2)}<i style="--w:${width(p.score)}" aria-hidden="true"></i></span>
          </div>
          <p class="passage">${highlight(p.chunk.text.replace(/^Section: .*\n/, ""), question)}</p>
        </div>
      </article>`).join("");
  }
  results.innerHTML = explain + readout + body + xray(r);
}

// Follow one passage across the four lanes.
results.addEventListener("pointerover", (e) => focusChip(e.target.closest(".chip")));
results.addEventListener("focusin", (e) => focusChip(e.target.closest(".chip")));
results.addEventListener("pointerleave", () => focusChip(null));
function focusChip(el) {
  const lanes = results.querySelector(".lanes");
  if (!lanes) return;
  lanes.classList.toggle("focus", Boolean(el));
  lanes.querySelectorAll(".chip").forEach((c) => c.classList.toggle("lit", Boolean(el) && c.dataset.id === el.dataset.id));
}

async function ask(question, k = null) {
  question = question.trim();
  if (!question || !ready) return;
  lastQuestion = question;
  button.disabled = true;
  if (!engine.reranker) setStatus("Your search will run as soon as the models finish loading…");
  try {
    await ready;
    render(question, await engine.search(question, { allow: allowed() }), k);
    setStatus("Ready.");
  } catch (e) {
    setStatus(`Search failed: ${e.message}. Reload the page to try again.`);
  } finally {
    button.disabled = false;
  }
}

form.addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });

const list = $(".examples");
for (const q of EXAMPLES) {
  const li = document.createElement("li");
  const b = document.createElement("button");
  b.type = "button"; b.textContent = q;
  b.addEventListener("click", () => { input.value = q; ask(q); });
  li.append(b); list.append(li);
}

// ---- orders ------------------------------------------------------------------
const ORDER_EXAMPLES = [
  "What's the status of order 1042?", "Track order 1043", "What's in order 1048?", "Which orders are late?",
  "Which orders are on hold?", "Show orders for Juniper Fulfillment", "What shipped last week?",
  "How many orders are in each status?",
];
const oform = $("#oask");
const oinput = $("#oq");
const obutton = oform.querySelector("button");
const oresults = $("#oresults");
let ordersDb = null, translator = null, octx = null, ordersReady = null, lastOrderQuestion = null;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error(`couldn't load ${src}`));
    document.head.append(s);
  });
}

const SQL_WORDS = /\b(SELECT|FROM|JOIN|ON|WHERE|AND|NOT|IN|IS|NULL|AS|ORDER BY|GROUP BY|COUNT|BETWEEN|DESC)\b/g;
function sqlHtml(sql, params) {
  return escape(sql).replace(SQL_WORDS, "<b>$1</b>")
    .replace(/:(\w+)/g, (m, n) => `<span class="param">:${n}</span>`);
}
// Prices get thousands separators; order numbers (4 digits) stay as typed.
const fmt = (v) => (v == null ? "—" : typeof v === "number" && v > 9999 ? v.toLocaleString("en-US") : String(v));

function cell(col, v, hidden) {
  if (hidden.has(col)) return `<span class="hidden">hidden</span>`;
  if (col === "status" || col === "event") return `<span class="st st-${escape(v)}">${escape(v)}</span>`;
  return escape(fmt(v));
}

function table(res, hidden) {
  if (!res.rows.length) return `<p class="empty-lane">No orders match${role.id === "contractor" ? " in the West region (all a Contractor can see)" : ""}.</p>`;
  // One wide row reads better as a card than as a table you scroll sideways.
  if (res.rows.length === 1 && res.columns.length > 4) {
    return `<dl class="record">${res.columns.map((c, i) =>
      `<div><dt>${escape(c)}</dt><dd>${cell(c, res.rows[0][i], hidden)}</dd></div>`).join("")}</dl>`;
  }
  const head = res.columns.map((c) => `<th${hidden.has(c) ? ' class="hidden"' : ""}>${escape(c)}</th>`).join("");
  const body = res.rows.map((row) => `<tr>${row.map((v, i) => `<td>${cell(res.columns[i], v, hidden)}</td>`).join("")}</tr>`).join("");
  return `<div class="tablewrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// The orders X-ray: which query type won and by how much, what was pulled
// out of the question, and what came back.
function oxray(t, res, access) {
  const slot = (name, v) => `<li class="chip${v ? " answer" : ""}"><i>${name}</i><span>${v ? escape(v) : "—"}</span></li>`;
  const p = t.slots.period;
  return `<details class="xray"><summary>Query X-ray<small>how the question became SQL</small></summary>
    <div class="lanes olanes">
      <div class="lane meaning"><h4>Query type, by meaning</h4><ol>${t.ranked.slice(0, 4).map(([intent, score], i) =>
        `<li class="chip${i === 0 && t.intent ? " answer" : ""}"><i>${i + 1}</i><span>${escape(intent.label)}</span><em>${score.toFixed(2)}</em></li>`).join("")}</ol></div>
      <div class="lane keyword"><h4>Values found</h4><ol>
        ${slot("order", t.slots.order)}${slot("customer", t.slots.customer?.name)}${slot("status", t.slots.status)}${slot("dates", p ? `${p.label} (${p.from} → ${p.to})` : null)}
      </ol></div>
      <div class="lane ranked"><h4>Result</h4><ol>
        <li class="chip answer"><i>rows</i><span>${res ? res.rows.length : 0}</span></li>
        <li class="chip"><i>role</i><span>${escape(role.label)}</span></li>
        ${access?.hidden.size ? `<li class="chip"><i>hidden</i><span>${escape([...access.hidden].join(", "))}</span></li>` : ""}
      </ol></div>
    </div></details>`;
}

async function askOrders(question, k = null) {
  question = question.trim();
  if (!question || !ready) return;
  lastOrderQuestion = question;
  obutton.disabled = true;
  try {
    await ready;
    await ordersReady;
    const access = applyRole(ordersDb, role.id);
    const t = await translator.translate(question, octx);
    const head = `<p class="readout">searched as <strong>${role.label}</strong>${t.intent ? ` · query type <strong>${escape(t.intent.label)}</strong> · match <strong>${t.score.toFixed(2)}</strong>` : ""}</p>`;

    if (access.denied) {
      oresults.innerHTML = head + `<div class="empty denied"><h3>No access to order data</h3><p>The ${role.label} role can't query orders. Switch role to see the difference.</p></div>`;
      return;
    }
    if (!t.intent) {
      oresults.innerHTML = head + `<div class="empty"><h3>That isn't an order question I can turn into a query</h3>
        <p>This demo's translator handles: ${INTENTS.map((i) => escape(i.label.toLowerCase())).join(" · ")}. The full app writes open-ended SQL with Claude.</p></div>` + oxray(t, null, access);
      return;
    }
    if (t.missing.length) {
      const hint = { order: "Which order? Add the order number, like 1042.", customer: "Which customer? Name them, like Juniper Fulfillment.",
        status: "Which status? For example shipped, picking, delivered or cancelled.", period: "When? For example last week, this week or October." }[t.missing[0]];
      oresults.innerHTML = head + `<div class="empty"><h3>One more detail</h3><p>${hint}</p></div>` + oxray(t, null, access);
      return;
    }

    const res = run(ordersDb, t.sql, t.params);
    const row = res.rows.length === 1 ? Object.fromEntries(res.columns.map((c, i) => [c, res.rows[0][i]])) : null;
    // A held or late order: find the policy that explains it.
    let why = null;
    if (row?.status) {
      const late = !row.delivered_at && !["cancelled", "returned"].includes(row.status) && row.promised_by < octx.today;
      const q = row.hold_reason ? `${row.hold_reason.replace(/_/g, " ")} hold` : late ? "order is late, contact the customer" : null;
      if (q) why = (await engine.search(q, { allow: allowed() })).passages[0] ?? null;
    }
    const docsOnly = k ? await engine.search(question, { allow: allowed() }) : null;
    const params = Object.entries(t.params).map(([n, v]) => `<span class="param">${escape(n)}</span> = ${escape(fmt(v))}`).join(" · ");
    const explain = k ? `<div class="explain"><b>What just happened</b>${k.explain({ docsOnly, row, why }).map((x) => `<p>${x}</p>`).join("")}</div>` : "";
    const whyHtml = why ? `<aside class="why"><b>Why · from ${escape(why.chunk.source)}</b>
      <p>${escape(why.chunk.text.replace(/^Section: .*\n/, ""))}</p></aside>` : "";
    // The answer first; the rows, the policy and the SQL below it as evidence.
    const sentence = `<p class="oanswer">${escape(summarize(t, res, octx, access.hidden))}</p>`;
    const sqlHtmlBlock = `<details class="xray sqlwrap"><summary>Show the SQL<small>what ran, with its values</small></summary>
      <div class="sqlblock"><pre><code>${sqlHtml(t.sql, t.params)}</code></pre><p class="params">${params || "no parameters"} · runs against your role's views</p></div></details>`;
    oresults.innerHTML = explain + sentence +
      `<div class="answer-grid${why ? " with-why" : ""}">${table(res, access.hidden)}${whyHtml}</div>` +
      head + sqlHtmlBlock + oxray(t, res, access);
  } catch (e) {
    oresults.innerHTML = `<div class="empty"><h3>The query failed</h3><p>${escape(e.message)}. Reload the page to try again.</p></div>`;
  } finally {
    obutton.disabled = false;
  }
}

oform.addEventListener("submit", (e) => { e.preventDefault(); askOrders(oinput.value); });
const olist = $("#orders .examples");
for (const q of ORDER_EXAMPLES) {
  const li = document.createElement("li");
  const b = document.createElement("button");
  b.type = "button"; b.textContent = q;
  b.addEventListener("click", () => { oinput.value = q; askOrders(q); });
  li.append(b); olist.append(li);
}

// ---- privacy meter ---------------------------------------------------------
// Counts every network request the page makes after the models are in
// memory. Searching should never add to it; anyone can check in DevTools.
function watchRequests() {
  const meter = $(".meter-privacy");
  const seen = [];
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) seen.push(new URL(entry.name).host);
    meter.querySelector("strong").textContent = seen.length;
    meter.classList.toggle("leaked", seen.length > 0);
    meter.title = seen.length ? `Requests to: ${[...new Set(seen)].join(", ")}` : "";
  }).observe({ type: "resource" });
}

(async () => {
  setStatus("Loading the document index…");
  const index = await (await fetch("index.json")).json();
  engine = new Engine(index);
  engine.files = index.files;
  showAccess();
  const loaded = {};
  setStatus("Loading search models (about 50 MB, once)…", 0);
  ready = engine.load((what, done, total) => {
    if (what === "embedder-ready") { button.disabled = false; return; }
    if (what === "reranker-ready") { setStatus("Ready."); return; }
    loaded[what] = done / total;
    const fraction = ((loaded.embedder ?? 0) + (loaded.reranker ?? 0)) / 2;
    setStatus("Loading search models (about 50 MB, once)…", fraction);
  });
  ready.catch((e) => setStatus(`Couldn't load the search models: ${e.message}. Check your connection and reload.`));

  // The orders database and SQLite load with everything else, before the
  // privacy meter starts, so querying orders adds no requests either.
  ordersReady = (async () => {
    await loadScript(`${SQLJS}sql-wasm.js`);
    const SQL = await window.initSqlJs({ locateFile: (f) => `${SQLJS}${f}` });
    const bytes = new Uint8Array(await (await fetch("orders.db")).arrayBuffer());
    ordersDb = new SQL.Database(bytes);
    octx = loadContext(ordersDb);
  })();
  await ready;
  translator = new Translator((t) => engine.embed(t));
  await Promise.all([ordersReady, translator.ready()]);
  obutton.disabled = false;
  watchRequests();
})();
