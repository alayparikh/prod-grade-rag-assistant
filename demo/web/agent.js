// "Ask the agent": plays back saved runs of the app's agent (agent.py).
//
// The full app's agent calls Claude, and this page calls nothing, so the page
// cannot run it. Instead demo/agent_runs.py ran each question once per role
// through the real agent loop and saved what happened - each step, what the
// step read, the answer - in agent.json. This file finds the saved question a
// visitor means and plays that run back. Nothing here generates text.
//
// Each run says which kind it is, and the page labels it:
//   "example"   saved; real tools and results; the steps and answer were scripted
//   "recorded"  saved; the real agent, model included, with its timings and cost
//   "live"      run just now in the browser for a question with no saved run
//               (liverun.js): fixed steps, no model
//
//   SavedRuns   matches a typed question to a saved one, by meaning
//   renderRun   draws one run as a tape of steps, then the answer

// Cosine similarity a typed question needs to count as a saved one.
// Measured on the golden set's paraphrases and look-alikes: rewordings of a
// saved question scored 0.60 to 0.93, but questions that only look similar
// reached 0.77 ("Where does Jane Doe work?" against the saved salary
// question). No value separates the two, so this sits above the look-alikes:
// a typed question that misses gets "no saved answer" and the list of
// questions, which is better than a confident answer to a different question.
// At 0.8, 8 of the 14 test paraphrases match. demo/check_search.mjs holds both
// sides on every deploy: no paraphrase may match the wrong question, and no
// look-alike may match at all.
export const MIN_MATCH_SCORE = 0.8;

const normalise = (text) => text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
// "Why is order 1043 late?" reads almost the same as the saved question about
// order 1042 and would replay the wrong order's answer, so the numbers in the
// two questions have to be the same ones.
const numbersIn = (text) => [...new Set(text.match(/\d+/g) ?? [])].sort().join(" ");
// Likewise "where are my orders?" is one word from the saved "where is my
// order?", but asks about a customer's orders, not one order: the reply it
// needs is different, so one order and many orders never match each other.
const ordersIn = (text) => (/\borders\b/i.test(text) ? "many" : /\border\b/i.test(text) ? "one" : "");

export class SavedRuns {
  constructor(data, embed) {
    this.data = data;
    this.embed = embed;          // (text) => normalised Float32Array
    this.vectors = null;
  }

  async ready() {
    if (this.vectors) return;
    this.vectors = [];
    for (const question of this.data.questions) {
      this.vectors.push({ question, v: await this.embed(question.question) });
    }
  }

  // { question } when a saved question matches; otherwise { question: null,
  // nearest, reason } where reason is "score", "numbers" or "orders".
  async match(text) {
    await this.ready();
    const exact = this.data.questions.find((q) => normalise(q.question) === normalise(text));
    if (exact) return { question: exact, score: 1, reason: null };
    const typed = await this.embed(text);
    let nearest = null, score = -1;
    for (const { question, v } of this.vectors) {
      const similarity = v.reduce((sum, x, i) => sum + x * typed[i], 0);
      if (similarity > score) { nearest = question; score = similarity; }
    }
    if (score < MIN_MATCH_SCORE) return { question: null, nearest, score, reason: "score" };
    if (numbersIn(text) !== numbersIn(nearest.question)) return { question: null, nearest, score, reason: "numbers" };
    if (ordersIn(text) !== ordersIn(nearest.question)) return { question: null, nearest, score, reason: "orders" };
    return { question: nearest, score, reason: null };
  }
}

// ---- rendering -------------------------------------------------------------
const escape = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const plural = (n, unit) => `${n} ${unit}${n === 1 ? "" : "s"}`;
const seconds = (ms) => `${(ms / 1000).toFixed(1)}s`;
const isRecorded = (data) => data.kind === "recorded";

// One colour per kind of step, the same ones the rest of the page uses:
// violet for document search, amber for the orders database.
const TOOLS = {
  query_orders: { label: "Queried orders", kind: "from-orders", unit: "row", reveal: "Show the SQL and rows" },
  search_docs: { label: "Searched documents", kind: "from-docs", unit: "passage", reveal: "Show the passages" },
  find_file: { label: "Looked for files", kind: "from-docs", unit: "file", reveal: "Show the files" },
};

const SQL_WORDS = /\b(SELECT|DISTINCT|FROM|LEFT JOIN|JOIN|ON|WHERE|AND|OR|NOT|IN|IS|NULL|AS|ORDER BY|GROUP BY|HAVING|COUNT|SUM|CASE|WHEN|THEN|ELSE|END|BETWEEN|LIKE|DESC|ASC|LIMIT|WITH)\b/g;
const cellText = (v) => (v == null ? "—" : typeof v === "number" && v > 9999 ? v.toLocaleString("en-US") : String(v));

function rowsHtml(detail) {
  if (!detail.rows.length) return `<p class="tnote">No rows this role can see matched.</p>`;
  const hidden = new Set(detail.hidden);
  const head = detail.columns.map((c) => `<th${hidden.has(c) ? ' class="hidden"' : ""}>${escape(c)}</th>`).join("");
  const body = detail.rows.map((row) => `<tr>${row.map((v, i) =>
    `<td>${hidden.has(detail.columns[i]) ? '<span class="hidden">hidden</span>' : escape(cellText(v))}</td>`).join("")}</tr>`).join("");
  return `<div class="tablewrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function evidenceHtml(step) {
  const d = step.detail;
  if (d.error) return `<p class="tnote">${escape(d.error)}</p>`;
  if (d.sql) {
    return `<div class="sqlblock"><pre><code>${escape(d.sql).replace(SQL_WORDS, "<b>$1</b>")}</code></pre></div>${rowsHtml(d)}`;
  }
  if (d.passages?.length) {
    return d.passages.map((p) => `<blockquote><cite>${escape(p.source)}${p.section ? ` · ${escape(p.section)}` : ""}</cite>${escape(p.text)}</blockquote>`).join("");
  }
  if (d.files?.length) return `<p class="tnote">${d.files.map((f) => escape(f.name)).join(" · ")}</p>`;
  // Deliberately one message: the agent is told the same thing whether a
  // passage doesn't exist or this role may not read it.
  return `<p class="tnote">Nothing this role can read matched.</p>`;
}

// The left edge of the tape: the measured time for a recorded run. An example
// run has no model in it, so its timings would mean nothing; it gets step numbers.
const mark = (data, ms, n) => (isRecorded(data) ? `T+${seconds(ms)}` : n);

function stepHtml(data, step, i) {
  const tool = TOOLS[step.tool] ?? { label: step.tool, kind: "from-docs", unit: "result", reveal: "Show the result" };
  const outcome = step.ok ? plural(step.count, tool.unit) : "refused";
  const query = step.tool === "search_docs" ? `<q>${escape(step.args.query ?? "")}</q>` : "";
  return `<li class="tstep ${tool.kind}${step.ok ? "" : " refused"}">
    <span class="tat">${mark(data, step.at_ms, `Step ${i + 1}`)}</span>
    <div class="tbody">
      <h4>${tool.label}<em>${outcome}</em></h4>${query}
      <details><summary>${tool.reveal}</summary>${evidenceHtml(step)}</details>
    </div></li>`;
}

// Answers are plain sentences with the odd **bold** and paragraph break;
// anything else is shown as written. Escaped first, so saved text can't
// inject markup.
function answerHtml(text) {
  return escape(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n{2,}/g, "</p><p>").replace(/\n/g, "<br>");
}

function stampHtml(data, run, role) {
  const facts = `as ${escape(role.label)} · ${plural(run.steps.length, "step")}`;
  if (data.kind === "live") {
    return `<p class="astamp"><b>Live run</b> ${facts} · no saved run for this question, so it ran just now in your
      browser: the same SQL templates and document search as the sections above, with fixed steps and no model.
      The answer is put together from what they returned</p>`;
  }
  if (isRecorded(data)) {
    return `<p class="astamp"><b>Recorded run</b> ${escape(data.made_at)} · ${escape(data.model)} · ${facts}
      · ${seconds(run.latency_ms)}${run.cost_usd == null ? "" : ` · $${run.cost_usd.toFixed(3)}`}</p>`;
  }
  return `<p class="astamp"><b>Example run</b> ${facts} · every query and passage is a real result from this data;
    the choice of steps and the answer's wording are scripted</p>`;
}

function runHtml({ data, question, run, role, typed }) {
  const replayed = normalise(typed) === normalise(question.question) ? "" :
    `<p class="amatch">Not the same words, so here is the saved question it matches: <strong>${escape(question.question)}</strong></p>`;
  const cited = [...run.sources.map((s) => `<span class="file">${escape(s)}</span>`),
    ...(run.used_orders ? [`<span class="file">orders database</span>`] : [])];
  const heading = run.clarification ? "The agent asked back" : "Answer";
  const tape = run.steps.length ? `<ol class="tape" aria-label="Steps the agent took">${run.steps.map((s, i) => stepHtml(data, s, i)).join("")}</ol>` :
    `<p class="tnote tape-empty">No steps: the agent stopped before reading anything.</p>`;
  return `${replayed}${tape}
    <div class="averdict${run.clarification ? " asked" : ""}">
      <span class="tat">${mark(data, run.latency_ms, "")}</span>
      <div><h4>${heading}</h4><div class="atext"><p>${answerHtml(run.answer)}</p></div>
      ${cited.length ? `<p class="asrc">From ${cited.join(" ")}</p>` : ""}</div>
    </div>
    ${stampHtml(data, run, role)}`;
}

// Playback pace. A recorded run plays at a quarter of its measured gaps, kept
// between two bounds so a 12-second run doesn't take 12 seconds and a fast
// step is still seen. An example run has no measured gaps, so it uses one.
const PLAYBACK_SCALE = 0.25;
const MIN_GAP_MS = 280;
const MAX_GAP_MS = 900;
const EXAMPLE_GAP_MS = 520;
const gap = (ms) => Math.max(MIN_GAP_MS, Math.min(MAX_GAP_MS, ms * PLAYBACK_SCALE));

// Draws the run into `el`. Every step is laid out at once and revealed in
// order, so nothing on the page moves while it plays. Returns a function that
// cancels the playback.
export function renderRun(el, view, { animate = true } = {}) {
  el.innerHTML = runHtml(view);
  const parts = [...el.querySelectorAll(".tstep, .averdict, .astamp")];
  if (!animate) return () => {};
  parts.forEach((part) => part.classList.add("pending"));
  const times = [...view.run.steps.map((s) => s.at_ms), view.run.latency_ms, view.run.latency_ms];
  const timers = [];
  let at = 0;
  parts.forEach((part, i) => {
    if (i === parts.length - 1) at += MIN_GAP_MS;
    else at += isRecorded(view.data) ? gap(times[i] - (times[i - 1] ?? 0)) : EXAMPLE_GAP_MS;
    timers.push(setTimeout(() => part.classList.remove("pending"), at));
  });
  return () => { timers.forEach(clearTimeout); parts.forEach((part) => part.classList.remove("pending")); };
}
