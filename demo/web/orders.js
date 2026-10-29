// Orders: plain-English questions → SQL, without a language model.
//
// A "pattern translator": the question is matched to one of a fixed set of
// query types by meaning (the same embedding model the document search
// uses), the order number / customer / status / dates are pulled out, and
// a parameterized SQL template is filled in. It never writes SQL from the
// question's text, so nothing typed can change what the query does. The
// full Python app does the open-ended version with Claude.
//
// Runs unchanged in the browser and in the Node CI check (demo/check_search.mjs).

// Below this cosine similarity to every example, the question isn't a query
// type we support, and the page says so instead of guessing. Calibrated on
// paraphrased test questions: supported ones scored 0.51+, document and
// off-topic questions at most 0.36.
export const MIN_INTENT_SCORE = 0.45;

export const INTENTS = [
  {
    id: "order_status", label: "Status of one order", needs: ["order"],
    examples: ["What is the status of order 1042?", "Where is order 1043?", "Why is order 1042 late?",
      "Has order 1046 been delivered?", "Is order 1050 shipped yet?", "What's happening with order 1044?"],
    sql: `SELECT o.id, c.name AS customer, o.status, o.hold_reason, o.placed_at,
       o.promised_by, o.shipped_at, o.delivered_at, o.carrier, o.tracking_no
FROM orders_v o JOIN customers_v c ON c.id = o.customer_id
WHERE o.id = :order`,
  },
  {
    id: "tracking", label: "Tracking history", needs: ["order"],
    examples: ["Track order 1043", "Show the shipping history for order 1043",
      "What tracking events does order 1043 have?", "When did order 1046 ship?"],
    sql: `SELECT s.event, s.at, s.location
FROM shipments_v s
WHERE s.order_id = :order
ORDER BY s.at, s.seq`,
  },
  {
    id: "order_items", label: "What's in an order", needs: ["order"],
    examples: ["What's in order 1048?", "Which robots are in order 1048?",
      "How many units are in order 1042?", "What did order 1048 cost?"],
    sql: `SELECT i.sku, p.model, i.qty, p.unit_price, i.qty * p.unit_price AS line_total
FROM order_items_v i JOIN products_v p ON p.sku = i.sku
WHERE i.order_id = :order`,
  },
  {
    id: "customer_orders", label: "A customer's orders", needs: ["customer"],
    examples: ["Show orders for Cobalt Bay Distribution", "What has Juniper Fulfillment ordered?",
      "List Kestrel Medical's orders", "Orders from Polaris Auto Parts"],
    sql: `SELECT o.id, o.placed_at, o.status, o.hold_reason, o.promised_by
FROM orders_v o JOIN customers_v c ON c.id = o.customer_id
WHERE c.id = :customer
ORDER BY o.placed_at DESC, o.id DESC`,
  },
  {
    id: "late_orders", label: "Late orders",
    examples: ["Which orders are late?", "Show overdue orders", "What orders missed their promised date?",
      "Which orders are behind schedule?"],
    sql: `SELECT o.id, c.name AS customer, o.status, o.hold_reason, o.promised_by
FROM orders_v o JOIN customers_v c ON c.id = o.customer_id
WHERE o.delivered_at IS NULL AND o.status NOT IN ('cancelled', 'returned')
  AND o.promised_by < :today
ORDER BY o.promised_by, o.id`,
  },
  {
    id: "on_hold", label: "Orders on hold",
    examples: ["Which orders are on hold?", "Why are orders on hold?", "Show held orders and the reason",
      "What orders are stuck?"],
    sql: `SELECT o.id, c.name AS customer, o.hold_reason, o.promised_by
FROM orders_v o JOIN customers_v c ON c.id = o.customer_id
WHERE o.status = 'on_hold'
ORDER BY o.promised_by, o.id`,
  },
  {
    id: "by_status", label: "Orders in one status", needs: ["status"],
    examples: ["Which orders are being picked?", "Show orders that have shipped", "List cancelled orders",
      "Which orders were returned?"],
    sql: `SELECT o.id, c.name AS customer, o.placed_at, o.promised_by
FROM orders_v o JOIN customers_v c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.placed_at DESC, o.id DESC`,
  },
  {
    id: "count_by_status", label: "Order counts by status",
    examples: ["How many orders are in each status?", "Count orders by status",
      "Give me a breakdown of order statuses", "How many orders do we have?"],
    sql: `SELECT o.status, COUNT(*) AS orders
FROM orders_v o
GROUP BY o.status
ORDER BY orders DESC, o.status`,
  },
  {
    id: "shipped_between", label: "Orders shipped in a period", needs: ["period"],
    examples: ["What shipped last week?", "Which orders shipped in October?", "What went out this week?",
      "Orders shipped in September"],
    sql: `SELECT o.id, c.name AS customer, o.shipped_at, o.carrier
FROM orders_v o JOIN customers_v c ON c.id = o.customer_id
WHERE o.shipped_at BETWEEN :from AND :to
ORDER BY o.shipped_at, o.id`,
  },
];

// Every ORDER BY ends in a unique key (id, or seq for a timeline). Sorting on a
// column that can tie leaves the database free to return tied rows in any
// order, and the summary sentence names rows[0] - so it has to be stable.

// ---- who may see what ------------------------------------------------------
// The same roles as the document search. Every template reads only these
// *_v views, rebuilt for the role before each query, so a role's limits hold
// whatever the question was. Hidden columns come back as NULL and are shown
// as "hidden"; rows outside the role's scope never exist in the view.
export const ORDER_ROLES = {
  admin: { scope: "1", hidden: [] },
  engineer: { scope: "1", hidden: ["email", "unit_price"] },
  hr: { scope: "0", hidden: [], denied: true },
  contractor: { scope: "region = 'west'", hidden: ["email", "unit_price"], note: "West-region orders only" },
};

export function applyRole(db, roleId) {
  const r = ORDER_ROLES[roleId] ?? ORDER_ROLES.contractor; // unknown role: narrowest access
  const hide = (col) => (r.hidden.includes(col) ? `NULL AS ${col}` : col);
  db.exec(`
    DROP VIEW IF EXISTS customers_v; DROP VIEW IF EXISTS orders_v; DROP VIEW IF EXISTS order_items_v;
    DROP VIEW IF EXISTS shipments_v; DROP VIEW IF EXISTS products_v;
    CREATE TEMP VIEW customers_v AS
      SELECT id, name, region, account_tier, ${hide("email")} FROM customers WHERE ${r.scope};
    CREATE TEMP VIEW orders_v AS
      SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers_v);
    CREATE TEMP VIEW order_items_v AS
      SELECT * FROM order_items WHERE order_id IN (SELECT id FROM orders_v);
    CREATE TEMP VIEW shipments_v AS
      SELECT * FROM shipments WHERE order_id IN (SELECT id FROM orders_v);
    CREATE TEMP VIEW products_v AS
      SELECT sku, model, ${hide("unit_price")}, lead_time_days FROM products;`);
  // Anything computed from a hidden column is hidden too.
  const hidden = new Set(r.hidden);
  if (hidden.has("unit_price")) hidden.add("line_total");
  return { hidden, denied: Boolean(r.denied), note: r.note ?? null };
}

// ---- pulling facts out of the question -----------------------------------------
const STATUS_WORDS = [
  [/\b(being picked|picking|picked)\b/i, "picking"], [/\bshipped\b/i, "shipped"],
  [/\bdelivered\b/i, "delivered"], [/\bcancel+ed\b/i, "cancelled"], [/\breturned\b/i, "returned"],
  [/\b(placed|new orders)\b/i, "placed"],
];
const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
  "october", "november", "december"];
const iso = (d) => d.toISOString().slice(0, 10);

function parsePeriod(q, today) {
  const t = new Date(`${today}T00:00:00Z`);
  const day = (n) => new Date(t.getTime() + n * 86400000);
  const monday = day(-((t.getUTCDay() + 6) % 7));
  const lower = q.toLowerCase();
  if (/\btoday\b/.test(lower)) return { from: today, to: today, label: "today" };
  if (/\byesterday\b/.test(lower)) return { from: iso(day(-1)), to: iso(day(-1)), label: "yesterday" };
  if (/\bthis week\b/.test(lower)) return { from: iso(monday), to: today, label: "this week" };
  if (/\blast week\b/.test(lower)) {
    const start = new Date(monday.getTime() - 7 * 86400000);
    return { from: iso(start), to: iso(new Date(start.getTime() + 6 * 86400000)), label: "last week" };
  }
  const days = lower.match(/\blast (\d{1,3}) days\b/);
  if (days) return { from: iso(day(-Number(days[1]))), to: today, label: `last ${days[1]} days` };
  const m = MONTHS.findIndex((name) => new RegExp(`\\b${name}\\b`).test(lower));
  if (m >= 0) {
    const year = t.getUTCFullYear() - (m > t.getUTCMonth() ? 1 : 0);
    const first = new Date(Date.UTC(year, m, 1)), last = new Date(Date.UTC(year, m + 1, 0));
    return { from: iso(first), to: iso(last), label: MONTHS[m][0].toUpperCase() + MONTHS[m].slice(1) };
  }
  return null;
}

// A customer is named if the question contains their full name or its first
// word ("Juniper", "Kestrel"); every first word in this data is distinctive.
function findCustomer(q, customers) {
  const lower = q.toLowerCase();
  return customers.find((c) => lower.includes(c.name.toLowerCase()))
    ?? customers.find((c) => new RegExp(`\\b${c.name.split(" ")[0].toLowerCase()}\\b`).test(lower))
    ?? null;
}

export function extractSlots(question, { customers, today }) {
  const order = question.match(/\b(\d{4})\b/)?.[1];
  const status = STATUS_WORDS.find(([re]) => re.test(question))?.[1] ?? null;
  return {
    order: order ? Number(order) : null,
    customer: findCustomer(question, customers),
    status,
    period: parsePeriod(question, today),
  };
}

// ---- translation ---------------------------------------------------------------
export class Translator {
  constructor(embed) {
    this.embed = embed;          // (text) => normalised Float32Array
    this.examples = null;
  }

  async ready() {
    if (this.examples) return;
    this.examples = [];
    for (const intent of INTENTS) {
      for (const text of intent.examples) this.examples.push({ intent, v: await this.embed(text) });
    }
  }

  // Returns the query it would run, or why it won't run one.
  async translate(question, ctx) {
    await this.ready();
    const slots = extractSlots(question, ctx);
    const q = await this.embed(question);
    const dot = (v) => v.reduce((s, x, i) => s + x * q[i], 0);
    // A question naming an order number is about that one order, so only the
    // one-order queries compete. Without a number every query type competes:
    // "where is my order?" should win a one-order query and ask for the
    // number, not fall through to some multi-order query.
    const best = new Map();
    for (const ex of this.examples) {
      const perOrder = ex.intent.needs?.includes("order") ?? false;
      if (slots.order && !perOrder) continue;
      best.set(ex.intent, Math.max(best.get(ex.intent) ?? -1, dot(ex.v)));
    }
    const ranked = [...best.entries()].sort((a, b) => b[1] - a[1]);
    const [intent, score] = ranked[0] ?? [null, 0];
    if (!intent || score < MIN_INTENT_SCORE) return { intent: null, score, slots, ranked };

    const missing = (intent.needs ?? []).filter((s) => !slots[s]);
    const values = {
      order: slots.order, customer: slots.customer?.id, status: slots.status,
      from: slots.period?.from, to: slots.period?.to, today: ctx.today,
    };
    const params = {};
    for (const [, name] of intent.sql.matchAll(/:(\w+)/g)) params[`:${name}`] = values[name];
    return { intent, score, slots, ranked, missing, sql: intent.sql, params };
  }
}

export function run(db, sql, params) {
  const stmt = db.prepare(sql);
  try {
    stmt.bind(params);
    const columns = stmt.getColumnNames();
    const rows = [];
    while (stmt.step()) rows.push(stmt.get());
    return { columns, rows };
  } finally {
    stmt.free();
  }
}

export function loadContext(db) {
  const customers = run(db, "SELECT id, name FROM customers", {}).rows.map(([id, name]) => ({ id, name }));
  const today = run(db, "SELECT value FROM meta WHERE key = 'today'", {}).rows[0][0];
  return { customers, today };
}

// ---- the answer, in a sentence ------------------------------------------------
// The page leads with this; the SQL and rows sit below as evidence. Written
// from the result rows only (there's no language model), so it can't say
// anything the query didn't return. Hidden columns stay hidden here too.
const STATUS_TEXT = {
  placed: "has been placed and is waiting to be picked",
  picking: "is being picked and configured at the warehouse",
  shipped: "has shipped",
  delivered: "was delivered",
  on_hold: "is on hold",
  cancelled: "was cancelled",
  returned: "was returned",
};
const human = (s) => String(s).replace(/_/g, " ");
const daysBetween = (a, b) => Math.round((new Date(`${b}T00:00:00Z`) - new Date(`${a}T00:00:00Z`)) / 86400000);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const money = (n) => `$${Number(n).toLocaleString("en-US")}`;

export function summarize(t, res, ctx, hidden = new Set()) {
  const rows = res.rows.map((r) => Object.fromEntries(res.columns.map((c, i) => [c, r[i]])));
  const s = t.slots;
  switch (t.intent.id) {
    case "order_status": {
      const o = rows[0];
      if (!o) return `There's no order ${s.order} among the orders you can see.`;
      let text = `Order ${o.id} for ${o.customer} ${STATUS_TEXT[o.status] ?? human(o.status)}`;
      if (o.status === "on_hold" && o.hold_reason) text += ` for ${human(o.hold_reason)}`;
      if (o.status === "shipped" && o.carrier) text += ` with ${o.carrier}${o.tracking_no ? ` (tracking ${o.tracking_no})` : ""}`;
      if (o.delivered_at) text += ` on ${o.delivered_at}`;
      text += ".";
      if (!o.delivered_at && !["cancelled", "returned"].includes(o.status) && o.promised_by < ctx.today) {
        text += ` It's ${plural(daysBetween(o.promised_by, ctx.today), "day")} late: it was promised by ${o.promised_by}.`;
      } else if (o.delivered_at && o.delivered_at > o.promised_by) {
        text += ` That was ${plural(daysBetween(o.promised_by, o.delivered_at), "day")} after the promised ${o.promised_by}.`;
      } else if (!o.delivered_at && !["cancelled", "returned"].includes(o.status)) {
        text += ` It's promised by ${o.promised_by}.`;
      }
      return text;
    }
    case "tracking": {
      if (!rows.length) return `There's no tracking history for order ${s.order} among the orders you can see.`;
      const last = rows[rows.length - 1];
      return `Order ${s.order}'s latest event is ${human(last.event)} on ${last.at} (${last.location}), after ${plural(rows.length - 1, "earlier event")}.`;
    }
    case "order_items": {
      if (!rows.length) return `There's no order ${s.order} among the orders you can see.`;
      const lines = rows.map((r) => `${r.qty} × ${r.model}`).join(" and ");
      const total = rows.reduce((sum, r) => sum + (r.line_total ?? 0), 0);
      return `Order ${s.order} contains ${lines}` +
        (hidden.has("line_total") ? ". Prices are hidden for your role." : `, ${money(total)} in total.`);
    }
    case "customer_orders": {
      const open = rows.filter((r) => !["delivered", "cancelled", "returned"].includes(r.status));
      if (!rows.length) return `${s.customer.name} has no orders you can see.`;
      const ids = open.slice(0, 3).map((r) => `${r.id} (${human(r.status)})`).join(", ");
      return `${s.customer.name} has ${plural(rows.length, "order")}; ` +
        (open.length ? `${open.length} still open: ${ids}${open.length > 3 ? ", …" : ""}.` : "none are still open.");
    }
    case "late_orders": {
      if (!rows.length) return "No orders are late right now.";
      const worst = rows[0];
      return `${plural(rows.length, "order")} ${rows.length === 1 ? "is" : "are"} late right now. The most overdue is ${worst.id} for ${worst.customer}, ` +
        `${plural(daysBetween(worst.promised_by, ctx.today), "day")} past its ${worst.promised_by} promise.`;
    }
    case "on_hold": {
      if (!rows.length) return "No orders are on hold.";
      const reasons = [...new Set(rows.map((r) => human(r.hold_reason)))].join(", ");
      return `${plural(rows.length, "order")} ${rows.length === 1 ? "is" : "are"} on hold, for: ${reasons}.`;
    }
    case "by_status":
      return rows.length ? `${plural(rows.length, "order")} ${rows.length === 1 ? "is" : "are"} ${human(s.status)}${rows.length ? `; the newest is ${rows[0].id} for ${rows[0].customer}` : ""}.`
        : `No orders are ${human(s.status)}.`;
    case "count_by_status": {
      const total = rows.reduce((sum, r) => sum + r.orders, 0);
      return `There are ${plural(total, "order")}: ${rows.map((r) => `${r.orders} ${human(r.status)}`).join(", ")}.`;
    }
    case "shipped_between":
      return rows.length ? `${plural(rows.length, "order")} shipped ${s.period.label} (${s.period.from} to ${s.period.to}).`
        : `Nothing shipped ${s.period.label} (${s.period.from} to ${s.period.to}).`;
    default:
      return `${plural(rows.length, "row")} matched.`;
  }
}
