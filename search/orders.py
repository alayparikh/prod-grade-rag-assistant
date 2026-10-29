"""Order questions, answered from the orders database with SQL written by Claude.

The browser demo uses a fixed set of query templates (demo/web/orders.js).
Here Claude writes the SQL, so the question can be anything - which is
exactly why nothing it writes is trusted:

1. The guard parses the SQL and accepts only one SELECT that reads the
   role views below, with a forced LIMIT. Anything else is rejected
   before it reaches the database.
2. It runs on a read-only connection, with a time budget.
3. The views are rebuilt for the asker's role before every query, so rows
   and columns outside that role do not exist for the query to read. A
   prompt-injected "select every email" gets NULLs, because the role's
   view has none to give.

Roles mirror ORDER_ROLES in demo/web/orders.js; the golden set's role cases
run against both.
"""
import os
import sqlite3
import time

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_SQL = os.path.join(ROOT, "eval", "fixtures", "orders.sql")
MAX_ROWS = 50
TIME_BUDGET_S = 2.0

ROLES = {
    "admin": {"scope": "1", "hidden": []},
    "engineer": {"scope": "1", "hidden": ["email", "unit_price"]},
    "contractor": {"scope": "region = 'west'", "hidden": ["email", "unit_price"]},
    "none": {"scope": "0", "hidden": [], "denied": True},
}
# Group -> order role, checked in this order; a user in none of them has no
# access to order data. On a NAS the "groups" are the SIDs indexer.acl
# resolves over LDAP, so the mapping is configured per company:
#   RAG_ORDER_GROUP_ROLES="S-1-5-21-...-512=admin,S-1-5-21-...-1104=contractor"
DEFAULT_GROUP_ROLES = [("Admins", "admin"), ("Engineering", "engineer"), ("Warehouse", "contractor")]


def load_group_roles():
    raw = os.environ.get("RAG_ORDER_GROUP_ROLES", "")
    pairs = [item.split("=", 1) for item in raw.split(",") if "=" in item]
    return [(g.strip(), r.strip()) for g, r in pairs] or DEFAULT_GROUP_ROLES

VIEWS = {
    "customers_v": ["id", "name", "region", "account_tier", "email"],
    "orders_v": ["id", "customer_id", "placed_at", "status", "hold_reason", "carrier",
                 "tracking_no", "promised_by", "shipped_at", "delivered_at"],
    "order_items_v": ["order_id", "sku", "qty"],
    "shipments_v": ["order_id", "seq", "event", "at", "location"],
    "products_v": ["sku", "model", "unit_price", "lead_time_days"],
}


class GuardError(ValueError):
    """The SQL was refused before it ran. The message says why."""


class Sql(BaseModel):
    answerable: bool = Field(description="False if the question isn't about orders, customers, "
                                         "products or shipments, or needs a value that wasn't given "
                                         "(e.g. no order number for one order's status).")
    query: str = Field(default="", description="One SQLite SELECT over the *_v views. Empty if not answerable.")
    clarification: str = Field(default="", description="If not answerable: what's missing, in one sentence.")


def role_for_groups(groups, mapping=None):
    # None means membership couldn't be resolved: no order access, not a guess.
    groups = set(groups or [])
    for group, role in mapping or load_group_roles():
        if group in groups:
            return role
    return "none"


# ---- database ----------------------------------------------------------------
def ensure_db(path):
    """Build the database from the fixture SQL if it isn't there (dev and demo).
    A real deployment points RAG_ORDERS_DB at its own read replica."""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with sqlite3.connect(path) as connection, open(FIXTURE_SQL) as f:
        connection.executescript(f.read())
    return path


def connect(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)


def apply_role(connection, role):
    r = ROLES.get(role, ROLES["none"])  # unknown role: no access
    hide = lambda col: f"NULL AS {col}" if col in r["hidden"] else col  # noqa: E731
    connection.executescript(f"""
        DROP VIEW IF EXISTS temp.customers_v; DROP VIEW IF EXISTS temp.orders_v;
        DROP VIEW IF EXISTS temp.order_items_v; DROP VIEW IF EXISTS temp.shipments_v;
        DROP VIEW IF EXISTS temp.products_v;
        CREATE TEMP VIEW customers_v AS
          SELECT id, name, region, account_tier, {hide('email')} FROM customers WHERE {r['scope']};
        CREATE TEMP VIEW orders_v AS
          SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers_v);
        CREATE TEMP VIEW order_items_v AS
          SELECT * FROM order_items WHERE order_id IN (SELECT id FROM orders_v);
        CREATE TEMP VIEW shipments_v AS
          SELECT * FROM shipments WHERE order_id IN (SELECT id FROM orders_v);
        CREATE TEMP VIEW products_v AS
          SELECT sku, model, {hide('unit_price')}, lead_time_days FROM products;""")
    return {"hidden": set(r["hidden"]), "denied": bool(r.get("denied"))}


def today(connection):
    return connection.execute("SELECT value FROM meta WHERE key = 'today'").fetchone()[0]


# ---- the guard -----------------------------------------------------------------
def guard(sql):
    """Return a safe version of `sql`, or raise GuardError."""
    if not sql or not sql.strip():
        raise GuardError("no query")
    # Comments are where "-- ignore the rest" tricks live; nothing legitimate needs them.
    if "--" in sql or "/*" in sql:
        raise GuardError("comments are not allowed")
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"not valid SQL: {e}") from e
    if len(statements) != 1:
        raise GuardError("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise GuardError(f"only SELECT is allowed, got {tree.key.upper()}")
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
                             exp.Alter, exp.Command, exp.Pragma, exp.Attach)):
            raise GuardError(f"{node.key.upper()} is not allowed")
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name
        if name in ctes:
            continue
        if name not in VIEWS:
            raise GuardError(f"table {name!r} is not readable (allowed: {', '.join(VIEWS)})")
    limit = tree.args.get("limit")
    current = int(limit.expression.name) if limit is not None and limit.expression.is_int else None
    if current is None or current > MAX_ROWS:
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="sqlite")


def run(connection, sql):
    deadline = time.monotonic() + TIME_BUDGET_S
    # Called every N VM steps; a non-zero return aborts the query.
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        cursor = connection.execute(sql)
        columns = [d[0] for d in cursor.description]
        return columns, cursor.fetchall()
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise GuardError(f"query exceeded the {TIME_BUDGET_S:.0f}s budget") from e
        raise GuardError(f"query failed: {e}") from e
    finally:
        connection.set_progress_handler(None, 0)


# ---- the prompt ----------------------------------------------------------------
def schema_prompt(connection):
    tables = "\n".join(f"  {view}({', '.join(cols)})" for view, cols in VIEWS.items())
    return f"""You translate questions about Acme Robotics orders into one SQLite SELECT.

Readable views (use only these):
{tables}

Facts:
- Today is {today(connection)}. Dates are TEXT 'YYYY-MM-DD'.
- orders_v.status is one of placed, picking, shipped, delivered, on_hold, cancelled, returned.
- hold_reason (only when on_hold): address_verification, credit_check, export_license,
  site_readiness, payment_failed.
- An order is late if delivered_at IS NULL, status NOT IN ('cancelled','returned') and
  promised_by < today; or if delivered_at > promised_by.
- shipments_v holds the tracking timeline: event in placed, picking, on_hold, shipped,
  in_transit, delivered, cancelled, returned. seq is each event's place in the order's
  timeline; order a timeline BY at, seq (events can share a date).
- When ordering rows, end the ORDER BY with a unique column (id) so ties are stable.
- "Late orders" with no other qualifier means late right now: not yet delivered.
- Weeks run Monday to Sunday; "last week" is the previous full week, "this week" runs
  from Monday to today.
- Customer names are in customers_v.name; match them with LIKE '%name%'.

Rules: one SELECT, no comments, no other tables. Prefer readable column names. If the
question isn't about orders, or needs a value it doesn't give, set answerable to false."""


def generate(llm, connection, question, config=None):
    structured = llm.with_structured_output(Sql)
    messages = [("system", schema_prompt(connection)), ("human", question)]
    return structured.invoke(messages, config=config) if config else structured.invoke(messages)


def why_query(columns, rows, today_iso):
    """For a single held or late order: what to search the policy docs for."""
    if len(rows) != 1:
        return None
    row = dict(zip(columns, rows[0]))
    if row.get("hold_reason"):
        return f"{row['hold_reason'].replace('_', ' ')} hold"
    late = (row.get("status") not in (None, "cancelled", "returned", "delivered")
            and row.get("promised_by") and row["promised_by"] < today_iso)
    return "order is late, contact the customer" if late else None
