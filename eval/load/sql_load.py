"""SQL load test: many concurrent order questions against a large orders DB.

    python eval/load/sql_load.py --orders 200000 --workers 16 --queries 2000
    python eval/load/sql_load.py --orders 200000 --indexes      # same, with reflex indexes

Builds a scaled copy of the fixture database (the 80 story orders plus N
synthetic ones, streamed in batches), then runs the production order path
for each question exactly as the app does - a fresh read-only connection,
the role's views, orders.guard(), orders.run() with its time budget - from
W threads at once. No model: the SQL is a fixed mix of realistic queries
plus the "bounded" cases from eval/adversarial/sql_attacks.yaml, so the
load is reproducible and free.

Measures throughput, p50/p95/p99 per query kind, budget timeouts and errors.
Fails if:
  - any query raises something other than GuardError (a crash under load),
  - an attack query runs longer than 3x the time budget (unbounded),
  - a contractor ever sees a non-west row (role views broken under load),
  - normal queries' p95 exceeds the time budget (--strict only: the budget
    is what a user waits; without indexes at large sizes this is expected
    to fail, which is the point of running it with and without).
"""
import argparse
import json
import os
import random
import resource
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import date, timedelta

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from search import orders  # noqa: E402

REGIONS = ["west", "central", "east", "eu"]
STATUSES = ["placed", "picking", "shipped", "delivered", "delivered", "delivered", "on_hold", "cancelled"]
HOLDS = ["address_verification", "credit_check", "export_license", "site_readiness", "payment_failed"]
TODAY = date(2026, 10, 28)

# What staff actually ask, as the model would write it (guard adds LIMIT).
WORKLOAD = {
    "order_by_id": "SELECT id, status, hold_reason, promised_by FROM orders_v WHERE id = {order_id}",
    "late_orders": ("SELECT id, customer_id, promised_by FROM orders_v WHERE delivered_at IS NULL "
                    "AND status NOT IN ('cancelled','returned') AND promised_by < '2026-10-28' "
                    "ORDER BY promised_by, id"),
    "held_by_reason": "SELECT hold_reason, count(*) AS n FROM orders_v WHERE status = 'on_hold' GROUP BY hold_reason",
    "customer_orders": ("SELECT o.id, o.status FROM orders_v o JOIN customers_v c ON c.id = o.customer_id "
                        "WHERE c.name LIKE '%{name}%' ORDER BY o.placed_at DESC, o.id"),
    "timeline": "SELECT event, at FROM shipments_v WHERE order_id = {order_id} ORDER BY at, seq",
    "status_counts": "SELECT status, count(*) FROM orders_v GROUP BY status ORDER BY status",
    "revenue_by_region": ("SELECT c.region, sum(i.qty * p.unit_price) FROM order_items_v i "
                          "JOIN orders_v o ON o.id = i.order_id JOIN customers_v c ON c.id = o.customer_id "
                          "JOIN products_v p ON p.sku = i.sku GROUP BY c.region"),
}
ROLES = ["admin", "admin", "engineer", "contractor"]


def build_db(path, extra_orders, extra_customers, with_indexes):
    with sqlite3.connect(path) as connection, open(orders.FIXTURE_SQL) as f:
        connection.executescript(f.read())
        rng = random.Random(42)
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
            ((cid, f"Synthetic Customer {cid}", rng.choice(REGIONS), rng.choice(["standard", "gold"]),
              f"ops{cid}@example.com") for cid in range(100, 100 + extra_customers)))

        def order_rows():
            for oid in range(100_000, 100_000 + extra_orders):
                placed = TODAY - timedelta(days=rng.randint(1, 900))
                status = rng.choice(STATUSES)
                promised = placed + timedelta(days=rng.randint(10, 30))
                shipped = placed + timedelta(days=5) if status in ("shipped", "delivered") else None
                delivered = promised + timedelta(days=rng.randint(-3, 4)) if status == "delivered" else None
                yield (oid, rng.randint(100, 99 + extra_customers), placed.isoformat(), status,
                       rng.choice(HOLDS) if status == "on_hold" else None, None, None, promised.isoformat(),
                       shipped.isoformat() if shipped else None, delivered.isoformat() if delivered else None)

        def flush(batch):
            connection.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
            connection.executemany("INSERT INTO order_items VALUES (?, ?, ?)",
                                   ((r[0], rng.choice(["PR-200", "PR-400", "PR-900"]), 1) for r in batch))
            connection.executemany("INSERT INTO shipments VALUES (?, 1, 'placed', ?, 'Acme order desk')",
                                   ((r[0], r[2]) for r in batch))

        batch = []
        for row in order_rows():
            batch.append(row)
            if len(batch) == 10_000:
                flush(batch)
                batch = []
        if batch:
            flush(batch)
        if with_indexes:
            # The indexes a team adds by reflex. Measured at 200k orders they
            # make this mix slower, not faster (PRODUCTION_READINESS.md, SQL
            # section): the questions are aggregates and ranges over most rows,
            # and status has seven values. Kept as an option because "add an
            # index" is the first fix people reach for; check EXPLAIN QUERY
            # PLAN on the real workload before adding one.
            connection.executescript("""
                CREATE INDEX orders_customer ON orders(customer_id);
                CREATE INDEX orders_status ON orders(status, promised_by);
                CREATE INDEX order_items_order ON order_items(order_id);
                CREATE INDEX customers_region ON customers(region);
                ANALYZE;""")
    return path


def attack_cases():
    with open(os.path.join(ROOT, "eval", "adversarial", "sql_attacks.yaml")) as f:
        return [c for c in yaml.safe_load(f) if c["expect"] == "bounded"]


def one_question(db, kind, sql, role):
    """The order path's database half, as answer_order_question runs it."""
    started = time.perf_counter()
    outcome, rows = "ok", []
    connection = orders.connect(db)
    try:
        orders.apply_role(connection, role)
        _, rows = orders.run(connection, orders.guard(sql))
    except orders.GuardError as e:
        outcome = "timeout" if "budget" in str(e) else "rejected"
    except Exception as e:  # noqa: BLE001 - exactly what the test is looking for
        outcome = f"crash:{type(e).__name__}:{e}"
    finally:
        connection.close()
    return kind, role, outcome, (time.perf_counter() - started) * 1000, rows


def run_load(db, workers, total, attack_ratio, seed, max_order_id):
    rng = random.Random(seed)
    attacks = attack_cases()
    jobs = []
    for _ in range(total):
        role = rng.choice(ROLES)
        if rng.random() < attack_ratio:
            case = rng.choice(attacks)
            jobs.append((f"attack:{case['id']}", case["sql"], case.get("role", role)))
        else:
            kind = rng.choice(list(WORKLOAD))
            sql = WORKLOAD[kind].format(order_id=rng.choice([1042, 1043, rng.randint(100_000, max_order_id)]),
                                        name=rng.choice(["Cobalt", "Juniper", "Synthetic Customer 1"]))
            jobs.append((kind, sql, role))
        # Sentinel: a contractor must only ever see west, whatever else runs.
        if rng.random() < 0.05:
            jobs.append(("role_check", "SELECT DISTINCT region FROM customers_v", "contractor"))

    results, lock, cursor = [], threading.Lock(), iter(jobs)

    def worker():
        while True:
            with lock:
                job = next(cursor, None)
            if job is None:
                return
            result = one_question(db, *job)
            with lock:
                results.append(result)

    started = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, time.perf_counter() - started


def pct(values, p):
    values = sorted(values)
    return round(values[max(1, -(-p * len(values) // 100)) - 1], 1) if values else None


def summarize(results, elapsed):
    by_kind = {}
    for kind, _, outcome, ms, _ in results:
        bucket = by_kind.setdefault("attack" if kind.startswith("attack") else kind,
                                    {"n": 0, "ms": [], "timeouts": 0, "rejected": 0, "crashes": 0})
        bucket["n"] += 1
        bucket["ms"].append(ms)
        bucket["timeouts"] += outcome == "timeout"
        bucket["rejected"] += outcome == "rejected"
        bucket["crashes"] += outcome.startswith("crash")
    kinds = {k: {"n": b["n"], "p50_ms": pct(b["ms"], 50), "p95_ms": pct(b["ms"], 95), "p99_ms": pct(b["ms"], 99),
                 "timeouts": b["timeouts"], "rejected": b["rejected"], "crashes": b["crashes"]}
             for k, b in sorted(by_kind.items())}
    normal = [ms for kind, _, _, ms, _ in results if not kind.startswith("attack") and kind != "role_check"]
    return {"questions": len(results), "elapsed_s": round(elapsed, 2),
            "questions_per_s": round(len(results) / elapsed, 1),
            "normal_p50_ms": pct(normal, 50), "normal_p95_ms": pct(normal, 95), "normal_p99_ms": pct(normal, 99),
            "kinds": kinds}


def check(results, summary, strict):
    problems = []
    crashes = [r for r in results if r[2].startswith("crash")]
    if crashes:
        problems.append(f"{len(crashes)} crash(es), e.g. {crashes[0][0]}: {crashes[0][2][:160]}")
    slow_attacks = [r for r in results if r[0].startswith("attack") and r[3] > orders.TIME_BUDGET_S * 3000]
    if slow_attacks:
        problems.append(f"{len(slow_attacks)} attack query(ies) ran past 3x the budget, e.g. {slow_attacks[0][0]}")
    leaks = [r for r in results if r[0] == "role_check" and r[2] == "ok" and {row[0] for row in r[4]} - {"west"}]
    if leaks:
        problems.append(f"contractor saw non-west regions {leaks[0][4]}")
    if strict and summary["normal_p95_ms"] and summary["normal_p95_ms"] > orders.TIME_BUDGET_S * 1000:
        problems.append(f"normal p95 {summary['normal_p95_ms']} ms is over the {orders.TIME_BUDGET_S}s budget")
    return problems


def main():
    parser = argparse.ArgumentParser(description="Concurrent load on the guarded order-query path")
    parser.add_argument("--orders", type=int, default=50_000, help="synthetic orders on top of the fixture")
    parser.add_argument("--customers", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--attack-ratio", type=float, default=0.1)
    parser.add_argument("--indexes", action="store_true",
                        help="add reflex indexes (customer_id, status+promised_by, ...) to measure their effect")
    parser.add_argument("--strict", action="store_true", help="also fail when normal p95 exceeds the budget")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--report")
    args = parser.parse_args()

    workdir = tempfile.mkdtemp(prefix="rag_sql_load_")
    try:
        started = time.perf_counter()
        db = build_db(os.path.join(workdir, "orders.db"), args.orders, args.customers, args.indexes)
        build_s = time.perf_counter() - started
        results, elapsed = run_load(db, args.workers, args.queries, args.attack_ratio, args.seed,
                                    100_000 + args.orders - 1)
        summary = summarize(results, elapsed)
        summary.update(orders=args.orders + 80, customers=args.customers + 12, workers=args.workers,
                       indexes=args.indexes, db_mb=round(os.path.getsize(db) / 1e6, 1),
                       build_s=round(build_s, 1), time_budget_s=orders.TIME_BUDGET_S)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        summary["peak_rss_mb"] = round(peak / 1e6 if sys.platform == "darwin" else peak / 1e3, 1)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    problems = check(results, summary, args.strict)
    summary["problems"] = problems
    print(json.dumps(summary, indent=2))
    if args.report:
        with open(args.report, "w") as f:
            json.dump(summary, f, indent=2)
    for problem in problems:
        print(f"FAIL {problem}")
    print("OK" if not problems else f"{len(problems)} check(s) failed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
