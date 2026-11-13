// Live agent runs, for questions that have no saved run (agent.js plays the
// saved ones back).
//
// There is no model on this page, so the steps are fixed rather than chosen:
//   1. an order question goes through the SQL translator (orders.js), under the
//      role's views, exactly as in the Orders section;
//   2. for held or late orders, the policy that explains them is found by
//      document search (search.js), under the role's document access;
//   3. anything else is a document search.
// The answer is put together from what those steps returned and nothing else.
// The run has the same shape as a saved one, so the page draws it the same way.
//
// No DOM: the page and the CI check (demo/check_search.mjs) run the same code.
import { applyRole, clarifyingQuestion, run, summarize } from "./orders.js";

// rag.NO_CONTEXT_ANSWER: the full app's words when nothing it can read answers.
export const NO_INFORMATION = "I don't have information on that in the indexed documents.";
const ORDERS_DENIED = "Your role has no access to order data.";
const LATE_QUERY = "order is late, contact the customer";
const MAX_POLICY_SEARCHES = 3;
const EXCERPT_SENTENCES = 2;
const CLOSED = new Set(["delivered", "cancelled", "returned"]);

const human = (s) => String(s).replace(/_/g, " ");
const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const withoutSection = (text) => text.replace(/^Section: .*\n/, "").trim();

function excerpt(text, sentences = EXCERPT_SENTENCES) {
  const body = withoutSection(text);
  return (body.match(/[^.!?]+[.!?]+(?=\s|$)/g) ?? [body]).slice(0, sentences).join("").trim();
}

// The query as it ran, with its values in place, for showing on the tape.
function filledSql(sql, params) {
  return sql.replace(/:(\w+)/g, (m, name) => {
    const v = params[`:${name}`];
    return typeof v === "number" ? String(v) : `'${String(v).replace(/'/g, "''")}'`;
  });
}

// What to look up in the policies for these rows: why they are late, then why
// each is held. Rows outside the role's views never reach here.
function policyQueries(t, rows, today) {
  const late = t.intent.id === "late_orders" ||
    rows.some((r) => r.status && !CLOSED.has(r.status) && !r.delivered_at && r.promised_by < today);
  const holds = [...new Set(rows.map((r) => r.hold_reason).filter(Boolean))].map((h) => `${human(h)} hold`);
  return [...(late ? [LATE_QUERY] : []), ...holds].slice(0, MAX_POLICY_SEARCHES);
}

async function timed(fn) {
  const started = performance.now();
  const value = await fn();
  return [value, Math.round(performance.now() - started)];
}

async function searchStep(engine, query, allow) {
  const [found, ms] = await timed(() => engine.search(query, { allow }));
  const passages = found.passages.map((p) => ({
    source: p.chunk.source, section: p.chunk.section, text: withoutSection(p.chunk.text), chunkId: p.id,
  }));
  return { tool: "search_docs", args: { query }, ok: true, count: passages.length, ms, detail: { passages } };
}

// The top passage of each search, once each, as "Section: excerpt".
function policyLines(steps) {
  const seen = new Set();
  const lines = [];
  for (const step of steps) {
    const top = step.detail.passages?.[0];
    if (!top || seen.has(top.chunkId)) continue;
    seen.add(top.chunkId);
    const section = top.section ? human(top.section.split(" > ").pop()) : top.source;
    lines.push({ text: `**${capital(section)}:** ${excerpt(top.text)}`, source: top.source });
  }
  return lines;
}

const result = (fields) => ({ answer: "", sources: [], used_orders: false, clarification: false, steps: [], ...fields });

async function documentRun(question, engine, allow) {
  const step = await searchStep(engine, question, allow);
  const top = step.detail.passages[0];
  if (!top) return result({ answer: NO_INFORMATION, steps: [step] });
  return result({ answer: excerpt(top.text, 3), sources: [top.source], steps: [step] });
}

// question, and { translator, octx, db, engine, roleId, allow } from the page.
export async function liveRun(question, { translator, octx, db, engine, roleId, allow }) {
  const access = applyRole(db, roleId);
  const t = await translator.translate(question, octx);
  if (!t.intent) return documentRun(question, engine, allow);
  if (t.missing.length) return result({ answer: clarifyingQuestion(t), clarification: true });
  if (access.denied) {
    // As in the full app: the refused step leaves nothing to answer from.
    const refused = { tool: "query_orders", args: {}, ok: false, count: 0, ms: 0, detail: { error: ORDERS_DENIED } };
    return result({ answer: NO_INFORMATION, steps: [refused] });
  }

  const [res, ms] = await timed(() => run(db, t.sql, t.params));
  const hidden = [...access.hidden].filter((c) => res.columns.includes(c));
  const query = { tool: "query_orders", args: {}, ok: true, count: res.rows.length, ms,
    detail: { sql: filledSql(t.sql, t.params), columns: res.columns, rows: res.rows, hidden } };
  const rows = res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));
  const searches = [];
  for (const q of policyQueries(t, rows, octx.today)) searches.push(await searchStep(engine, q, allow));
  const lines = policyLines(searches);
  return result({
    answer: [summarize(t, res, octx, access.hidden), ...lines.map((l) => l.text)].join("\n\n"),
    sources: [...new Set(lines.map((l) => l.source))].sort(),
    used_orders: true,
    steps: [query, ...searches],
  });
}
