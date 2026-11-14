// Runs the golden set through the browser's search code (demo/web/search.js)
// so the JavaScript copy of the query pipeline cannot drift from the Python
// one unnoticed. CI fails if this exits non-zero.
//
//   python demo/build_index.py                      # writes index.json + golden.json
//   npm install --prefix demo/.node @huggingface/transformers@3.7.1 sql.js@1.15.2
//   node demo/check_search.mjs
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { Engine } from "./web/search.js";
import { Translator, applyRole, loadContext, run, summarize } from "./web/orders.js";
import { ROLES } from "./web/roles.js";
import { SavedRuns, followUp } from "./web/agent.js";
import { liveRun } from "./web/liverun.js";

const require = createRequire(new URL("./.node/", import.meta.url));
// Node resolves the package's CommonJS build; its exports sit on `default`.
const mod = await import(require.resolve("@huggingface/transformers"));
const lib = mod.pipeline ? mod : mod.default;

const index = JSON.parse(readFileSync(new URL("./web/index.json", import.meta.url)));
const golden = JSON.parse(readFileSync(new URL("./golden.json", import.meta.url)));

// Cases offline search cannot pass by design: there is no model to count,
// to resolve "they" in a follow-up, or to notice that a resume about Jane
// says nothing about her salary. The Python --live eval covers these.
const NEEDS_A_MODEL = new Set([
  "negative-salary", "safety-prompt-injection", "roster-count-engineers",
]);

const engine = new Engine(index);
await engine.load(null, lib);

// The orders database, from the same SQL the page's orders.db is built from.
const SQL = await require("sql.js")();
const db = new SQL.Database();
db.exec(readFileSync(new URL("../eval/fixtures/orders.sql", import.meta.url), "utf8"));
const octx = loadContext(db);
const translator = new Translator((t) => engine.embed(t));

// Mirrors askOrders() in app.js: translate, run under the role's views, and
// for a held order fetch the policy passage that explains the hold.
async function checkOrders(item) {
  const access = applyRole(db, item.role ?? "admin");
  if (item.expect_denied) return [access.denied, "expected the role to be denied"];
  const t = await translator.translate(item.question, octx);
  if (item.expect_no_query) return [!t.intent, `expected no query, got ${t.intent?.id} (${t.score.toFixed(2)})`];
  if (!t.intent) return [false, `no query type matched (best ${t.score.toFixed(2)})`];
  if (item.expect_missing) return [t.missing.includes(item.expect_missing), `expected to ask for ${item.expect_missing}`];
  if (t.missing.length) return [false, `${t.intent.id} is missing ${t.missing}`];
  const res = run(db, t.sql, t.params);
  const rows = res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));
  if (item.expect_rows !== undefined && rows.length !== item.expect_rows)
    return [false, `${t.intent.id}: expected ${item.expect_rows} rows, got ${rows.length}`];
  if (item.expect_values && !rows.some((row) => Object.entries(item.expect_values).every(([k, v]) => row[k] === v)))
    return [false, `${t.intent.id}: no row with ${JSON.stringify(item.expect_values)}`];
  const last = item.expect_last_values;
  if (last && !Object.entries(last).every(([k, v]) => rows.at(-1)?.[k] === v))
    return [false, `${t.intent.id}: last row ${JSON.stringify(rows.at(-1))} isn't ${JSON.stringify(last)}`];
  const sentence = summarize(t, res, octx, access.hidden);
  for (const phrase of item.expect_summary_contains ?? []) {
    if (!sentence.includes(phrase)) return [false, `answer "${sentence}" lacks "${phrase}"`];
  }
  for (const phrase of item.expect_summary_not_contains ?? []) {
    if (sentence.includes(phrase)) return [false, `answer "${sentence}" leaks "${phrase}"`];
  }
  if (item.expect_why_contains) {
    const reason = rows[0]?.hold_reason;
    const why = reason ? (await engine.search(`${reason.replace(/_/g, " ")} hold`)).passages[0] : null;
    if (!why?.chunk.text.toLowerCase().includes(item.expect_why_contains.toLowerCase()))
      return [false, `the policy passage for ${reason} didn't contain "${item.expect_why_contains}"`];
  }
  return [true, `${t.intent.id} → ${rows.length} rows · "${sentence.slice(0, 70)}"`];
}

let failed = 0, checked = 0;
for (const item of golden) {
  if (item.mode === "orders") {
    const [ok, why] = await checkOrders(item);
    checked++;
    if (!ok) failed++;
    console.log(`${ok ? "PASS" : "FAIL"}  ${item.id.padEnd(30)} ${why}`);
    continue;
  }
  // Agent cases are answered by Claude in the full app; the page replays
  // saved runs of them, checked separately below.
  if (item.mode === "agent") continue;
  if (item.mode === "find_file" || item.turns || NEEDS_A_MODEL.has(item.id)) continue;
  const r = await engine.search(item.question);
  const text = r.passages.map((p) => p.chunk.text).join("\n").toLowerCase();
  let ok = true, why = "";
  if (item.expect_refusal) {
    ok = r.passages.length === 0;
    why = `expected no passage, got ${r.passages.map((p) => p.chunk.source).join(", ")}`;
  } else if (item.expect_answer_contains_any) {
    ok = item.expect_answer_contains_any.some((k) => text.includes(k.toLowerCase()));
    why = `none of ${JSON.stringify(item.expect_answer_contains_any)} in the top passages`;
  } else if (item.expect_answer_contains_all) {
    ok = item.expect_answer_contains_all.every((k) => text.includes(k.toLowerCase()));
    why = `not all of ${JSON.stringify(item.expect_answer_contains_all)} in the top passages`;
  }
  checked++;
  if (!ok) failed++;
  const top = r.passages[0];
  console.log(`${ok ? "PASS" : "FAIL"}  ${item.id.padEnd(30)} ${ok ? (top ? `${top.chunk.source} (${top.score.toFixed(2)})` : "refused") : why}`);
}
// ---- the saved agent runs ----------------------------------------------------
// agent.json is built from the real agent loop by demo/agent_runs.py; its
// --check covers freshness and per-role leaks. Checked here, in the browser's
// own code: the page's document rules are the ones the runs were made under,
// and a typed question replays the right saved answer or none.
// A wrong answer is the failure that matters, so a paraphrase that finds
// nothing is tolerated (down to MIN_PARAPHRASE_RECALL) and one that finds a
// different question is not.
const MIN_PARAPHRASE_RECALL = 0.5; // measured: 8 of 14 at the page's threshold
const report = (ok, id, why) => {
  checked++;
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${id.padEnd(30)} ${why}`);
};
const agentFile = new URL("./web/agent.json", import.meta.url);
if (!existsSync(agentFile)) {
  report(false, "agent-runs", "demo/web/agent.json is missing; build it with python demo/agent_runs.py");
} else {
  const data = JSON.parse(readFileSync(agentFile));
  for (const r of ROLES) {
    const page = index.files.filter(r.can).sort().join(",");
    const built = [...(data.roles[r.id]?.files ?? [])].sort().join(",");
    report(page === built, `agent-role-${r.id}`, page === built ? `${page.split(",").length} files, as in agent.json`
      : "roles.js and agent.json disagree on which files this role can open");
  }
  const saved = new SavedRuns(data, (t) => engine.embed(t));
  let found = 0, paraphrases = 0;
  for (const item of golden.filter((g) => g.mode === "agent" && g.demo)) {
    const exact = await saved.match(item.question);
    const runs = Object.keys(exact.question?.runs ?? {});
    const complete = exact.question?.id === item.id && ROLES.every((r) => runs.includes(r.id));
    report(complete, item.id, complete ? `runs for ${runs.join(", ")}` : "no saved run of this question for every role");
    for (const text of item.paraphrases ?? []) {
      paraphrases++;
      const m = await saved.match(text);
      if (m.question?.id === item.id) found++;
      else if (m.question) report(false, item.id, `"${text}" replays the answer to ${m.question.id}`);
    }
    for (const text of item.look_alikes ?? []) {
      const m = await saved.match(text);
      report(!m.question, `${item.id}~`, m.question ? `"${text}" replays ${m.question.id} (${m.score.toFixed(2)})`
        : `"${text.slice(0, 44)}" finds nothing (${m.score.toFixed(2)}, ${m.reason})`);
    }
  }
  report(found >= paraphrases * MIN_PARAPHRASE_RECALL, "agent-paraphrase-recall", `${found} of ${paraphrases} rewordings found their question`);

  // ---- live agent runs ------------------------------------------------------
  // A question with no saved run runs live (liverun.js). The demo_live cases
  // must not hit a saved run, and their live run must meet the same
  // expectations the Python --live eval holds the real agent to.
  for (const item of golden.filter((g) => g.mode === "agent" && g.demo_live)) {
    const m = await saved.match(item.question);
    if (m.question) { report(false, `${item.id}*`, `replays saved ${m.question.id} instead of running live`); continue; }
    const r = ROLES.find((x) => x.id === (item.role ?? "admin"));
    const live = await liveRun(item.question, { translator, octx, db, engine, roleId: r.id, allow: new Set(index.files.filter(r.can)) });
    const [ok, why] = checkAgentRun(item, live);
    report(ok, `${item.id}*`, ok ? `live as ${r.id}: ${live.steps.map((s) => s.tool).join(" → ") || "asked back"} · "${live.answer.slice(0, 50)}"` : why);
  }

  // ---- the chat's follow-up rule ----------------------------------------------
  // The agent asks back, and a short reply completes the question; a new
  // question is left alone and never inherits the old one.
  const admin = ROLES.find((x) => x.id === "admin");
  const live = (q) => liveRun(q, { translator, octx, db, engine, roleId: admin.id, allow: new Set(index.files.filter(admin.can)) });
  const opening = "Where are my orders?";
  const first = await live(opening);
  report(first.clarification, "chat-asks-back", first.clarification ? `"${first.answer}"` : "expected a question back");
  const customer = db.exec("SELECT name FROM customers ORDER BY id LIMIT 1")[0].values[0][0];
  const joined = followUp(opening, customer);
  const second = await live(joined);
  const answered = !second.clarification && second.steps[0]?.tool === "query_orders" && second.steps[0].count > 0;
  report(answered, "chat-follow-up", answered ? `"${customer}" → ${second.steps[0].count} rows` : `"${joined}" did not query that customer's orders`);
  // A document answer is the part of the passage that answers, not its opening.
  const linkedin = await live("What is Sam Rivera's LinkedIn?");
  const linked = linkedin.answer.includes("linkedin.example.com/in/sam-rivera");
  report(linked, "chat-answer-from-passage", linked ? `"${linkedin.answer}"` : `answered "${linkedin.answer.slice(0, 60)}"`);
  const fresh = "How long are database backups kept?";
  report(followUp(opening, fresh) === fresh, "chat-new-question", "a new question does not inherit the pending one");
}

// eval/run_eval.py check_agent_result, for a run in the page's format.
function checkAgentRun(item, run) {
  const lower = run.answer.toLowerCase();
  if (item.expect_clarification) return [run.clarification, `expected a clarifying question, got "${run.answer.slice(0, 60)}"`];
  const worked = run.steps.filter((s) => s.ok);
  const used = new Set(worked.map((s) => s.tool));
  const missing = (item.expect_tools ?? []).filter((t) => !used.has(t));
  if (missing.length) return [false, `no result from ${missing} (used ${[...used]})`];
  const forbidden = (item.expect_no_tools ?? []).filter((t) => used.has(t));
  if (forbidden.length) return [false, `${forbidden} returned a result and should not have`];
  const rows = worked.flatMap((s) => s.detail.rows ?? []);
  if (item.expect_row_values && !rows.some((row) => item.expect_row_values.every((v) => row.includes(v))))
    return [false, `no query returned a row with ${JSON.stringify(item.expect_row_values)}`];
  if (item.expect_sources_any && !item.expect_sources_any.some((f) => run.sources.includes(f)))
    return [false, `cited ${run.sources}, expected one of ${item.expect_sources_any}`];
  if (item.expect_answer_contains_all && !item.expect_answer_contains_all.every((k) => lower.includes(k.toLowerCase())))
    return [false, `answer lacks one of ${item.expect_answer_contains_all}: "${run.answer.slice(0, 80)}"`];
  if (item.expect_answer_contains_any && !item.expect_answer_contains_any.some((k) => lower.includes(k.toLowerCase())))
    return [false, `answer has none of ${item.expect_answer_contains_any}`];
  if (item.expect_answer_not_contains_any?.some((k) => lower.includes(k.toLowerCase())))
    return [false, `answer leaks one of ${item.expect_answer_not_contains_any}`];
  if (item.expect_refusal && !lower.includes("don't have information")) return [false, `expected a refusal, got "${run.answer.slice(0, 60)}"`];
  return [true, ""];
}

console.log(`\n${checked - failed} passed, ${failed} failed`);
// Release the ONNX sessions first: exiting with them open aborts the
// process in onnxruntime's teardown, and a crash would fail CI on a pass.
await engine.embedder.dispose();
await engine.reranker.model.dispose();
process.exitCode = failed ? 1 : 0;
