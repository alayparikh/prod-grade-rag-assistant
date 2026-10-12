import { Engine, tokenize } from "./search.js";

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
  { id: "contractor", label: "Contractor", can: (f) => ["company_handbook.md", "onboarding_guide.md", "testing_standards.md"].includes(f) },
];
let role = ROLES[0];
const allowed = () => new Set(engine.files.filter(role.can));

const seg = $(".roles .seg");
for (const r of ROLES) {
  seg.insertAdjacentHTML("beforeend",
    `<label><input type="radio" name="role" value="${r.id}" ${r === role ? "checked" : ""}><span>${r.label}</span></label>`);
}
function showAccess() {
  if (!engine) return;
  const open = allowed().size, hidden = engine.files.length - open, el = $(".access");
  el.textContent = hidden ? `Can open ${open} of ${engine.files.length} files · ${hidden} hidden from this role`
                          : `Can open all ${open} files`;
  el.classList.toggle("blocked", hidden > 0);
}
function setRole(id) {
  role = ROLES.find((r) => r.id === id);
  seg.querySelector(`input[value="${id}"]`).checked = true;
  showAccess();
}
seg.addEventListener("change", (e) => {
  setRole(e.target.value);
  if (lastQuestion) ask(lastQuestion); // same question, new permissions
});

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
    input.value = k.question;
    $("#try").scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
    ask(k.question, k);
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
    if (what === "reranker-ready") { setStatus("Ready."); watchRequests(); return; }
    loaded[what] = done / total;
    const fraction = ((loaded.embedder ?? 0) + (loaded.reranker ?? 0)) / 2;
    setStatus("Loading search models (about 50 MB, once)…", fraction);
  });
  ready.catch((e) => setStatus(`Couldn't load the search models: ${e.message}. Check your connection and reload.`));
})();
