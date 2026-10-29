// Runs the golden set through the browser's search code (demo/web/search.js)
// so the JavaScript copy of the query pipeline cannot drift from the Python
// one unnoticed. CI fails if this exits non-zero.
//
//   python demo/build_index.py                      # writes index.json + golden.json
//   npm install --prefix demo/.node @huggingface/transformers@3.7.1 sql.js@1.15.2
//   node demo/check_search.mjs
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { Engine } from "./web/search.js";
import { Translator, applyRole, loadContext, run, summarize } from "./web/orders.js";

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
console.log(`\n${checked - failed} passed, ${failed} failed`);
// Release the ONNX sessions first: exiting with them open aborts the
// process in onnxruntime's teardown, and a crash would fail CI on a pass.
await engine.embedder.dispose();
await engine.reranker.model.dispose();
process.exitCode = failed ? 1 : 0;
