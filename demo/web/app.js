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
let ready = null; // resolves once both models have loaded

const escape = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

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

function render(question, r) {
  const cfg = engine.config;
  const ms = (x) => `${Math.round(x)} ms`;
  const readout = `<p class="readout">meaning <strong>${r.vector.length}</strong> · exact words <strong>${r.keyword.length}</strong>
    · merged <strong>${r.fused.length}</strong> · reranked in <strong>${ms(r.timings.rerank ?? 0)}</strong>
    · total <strong>${ms(r.timings.total)}</strong></p>`;

  if (!r.passages.length) {
    const best = r.ranked[0]?.score;
    results.innerHTML = readout + `<div class="empty"><h3>The documents don't cover this</h3>
      <p>The closest passage scored ${best?.toFixed(1)}; a passage needs ${cfg.min_score} or higher to count as an answer.</p></div>`;
    return;
  }
  // Scores are logits; the bar shows where each sits between the cutoff and
  // a confident match (about +6) for this reranker.
  const width = (s) => `${Math.round(Math.max(0, Math.min(1, (s - cfg.min_score) / (6 - cfg.min_score))) * 100)}%`;
  results.innerHTML = readout + r.passages.map((p, i) => `
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

async function ask(question) {
  question = question.trim();
  if (!question || !ready) return;
  button.disabled = true;
  if (!engine.reranker) setStatus("Your search will run as soon as the models finish loading…");
  try {
    await ready;
    render(question, await engine.search(question));
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

(async () => {
  setStatus("Loading the document index…");
  const index = await (await fetch("index.json")).json();
  engine = new Engine(index);
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
})();
