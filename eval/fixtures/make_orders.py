"""Generate eval/fixtures/orders.sql: Acme Robotics' fictional orders database.

Deterministic (fixed seed, fixed "today"), so every question about it has
one right answer forever. Lead and transit times come from the same numbers
the documents state (product_catalog.md, shipping_policy.md), so a promised
date in the data can always be explained by a passage in the docs.

    python eval/fixtures/make_orders.py      # rewrites orders.sql
"""
import os
import random
from datetime import date, timedelta

TODAY = date(2026, 10, 28)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orders.sql")

PRODUCTS = [  # sku, model, unit_price, lead time in business days
    ("PR-200", "PR-200 Tote Runner", 38000, 10),
    ("PR-400", "PR-400 Pallet Runner", 64000, 14),
    ("PR-900", "PR-900 Heavy Runner", 112000, 21),
]
LEAD = {sku: lead for sku, _, _, lead in PRODUCTS}
TRANSIT = {"west": 3, "central": 3, "east": 4, "eu": 7}
CARRIER = {"west": ("FreightLine", "FL"), "central": ("FreightLine", "FL"),
           "east": ("Coastal Haul", "CH"), "eu": ("EuroRoute", "ER")}

CUSTOMERS = [  # id, name, region, tier
    (1, "Cobalt Bay Distribution", "west", "gold"),
    (2, "Juniper Fulfillment", "east", "platinum"),
    (3, "Redstone Warehousing", "central", "standard"),
    (4, "Meridian Parts Co.", "eu", "gold"),
    (5, "Tallgrass Foods DC", "central", "standard"),
    (6, "Ironwood Supply", "east", "standard"),
    (7, "Lakeside Pharma Logistics", "eu", "platinum"),
    (8, "Granite Peak Retail", "west", "standard"),
    (9, "Silverline Apparel DC", "west", "gold"),
    (10, "Ember Grocery Hub", "west", "standard"),
    (11, "Polaris Auto Parts", "central", "gold"),
    (12, "Kestrel Medical Supply", "east", "platinum"),
]
REGION = {cid: region for cid, _, region, _ in CUSTOMERS}


def business_days(start, n):
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


# Orders with a story, so the demo's questions have interesting answers.
# (id, customer, placed, items, status, hold_reason, delivered_offset_days)
STORIES = [
    (1042, 1, date(2026, 9, 28), [("PR-400", 3)], "on_hold", "address_verification", None),
    (1043, 2, date(2026, 9, 21), [("PR-200", 8)], "shipped", None, None),            # shipped, late
    (1044, 7, date(2026, 9, 14), [("PR-900", 2)], "on_hold", "export_license", None),
    (1045, 3, date(2026, 10, 12), [("PR-400", 6)], "on_hold", "credit_check", None),
    (1046, 10, date(2026, 9, 8), [("PR-200", 4)], "delivered", None, -2),            # early
    (1047, 12, date(2026, 8, 17), [("PR-400", 2)], "returned", None, 0),
    (1048, 11, date(2026, 10, 1), [("PR-900", 1), ("PR-400", 2)], "on_hold", "site_readiness", None),
    (1049, 8, date(2026, 10, 20), [("PR-200", 2)], "on_hold", "payment_failed", None),
    (1050, 4, date(2026, 10, 21), [("PR-400", 3)], "picking", None, None),
    (1051, 9, date(2026, 9, 1), [("PR-400", 5)], "delivered", None, 3),              # delivered late
]


def build():
    rng = random.Random(1042)
    orders, items = [], []
    story_ids = {s[0] for s in STORIES}
    stories = {s[0]: s for s in STORIES}

    for oid in range(1001, 1081):
        if oid in story_ids:
            _, cid, placed, its, status, hold, dlv = stories[oid]
        else:
            cid = rng.randint(1, 12)
            placed = TODAY - timedelta(days=rng.randint(3, 120))
            while placed.weekday() >= 5:
                placed -= timedelta(days=1)
            its = [(rng.choice(["PR-200", "PR-400", "PR-400", "PR-900"]), rng.randint(1, 6))]
            hold, dlv = None, None
            age = (TODAY - placed).days
            if rng.random() < 0.06:
                status = "cancelled"
            elif age > 45:
                status, dlv = "delivered", rng.choice([-1, 0, 0, 0, 1])
            elif age > 25:
                status = rng.choice(["delivered", "delivered", "shipped"])
                dlv = rng.choice([-1, 0, 0, 2]) if status == "delivered" else None
            elif age > 8:
                status = rng.choice(["picking", "shipped"])
            else:
                status = rng.choice(["placed", "picking"])

        region = REGION[cid]
        lead = max(LEAD[sku] for sku, _ in its)
        promised = business_days(placed, lead + TRANSIT[region])
        carrier, prefix = CARRIER[region]
        shipped_at = business_days(placed, lead) if status in ("shipped", "delivered", "returned") else None
        tracking = f"{prefix}-{rng.randint(10**7, 10**8 - 1)}" if shipped_at else None
        delivered = None
        if status in ("delivered", "returned"):
            delivered = promised + timedelta(days=dlv or 0)
            delivered = min(delivered, TODAY - timedelta(days=1))
        orders.append(dict(id=oid, customer_id=cid, placed_at=placed, status=status, hold_reason=hold,
                           carrier=carrier if shipped_at else None, tracking_no=tracking,
                           promised_by=promised, shipped_at=shipped_at, delivered_at=delivered))
        for sku, qty in its:
            items.append((oid, sku, qty))
    return orders, items


def shipments(o):
    """A plausible tracking timeline for one order."""
    ev = [("placed", o["placed_at"], "Acme order desk")]
    if o["status"] == "cancelled":
        return ev + [("cancelled", business_days(o["placed_at"], 2), "Acme order desk")]
    if o["status"] != "placed":
        ev.append(("picking", business_days(o["placed_at"], 1), "Acme DC, Reno NV"))
    if o["status"] == "on_hold":
        ev.append(("on_hold", business_days(o["placed_at"], 3), f"hold: {o['hold_reason']}"))
    if o["shipped_at"]:
        ev.append(("shipped", o["shipped_at"], f"{o['carrier']} pickup, Reno NV"))
        mid = business_days(o["shipped_at"], 1)
        if mid < TODAY:
            ev.append(("in_transit", mid, f"{o['carrier']} hub"))
    if o["delivered_at"]:
        ev.append(("delivered", o["delivered_at"], "customer site"))
    if o["status"] == "returned":
        ev.append(("returned", min(o["delivered_at"] + timedelta(days=20), TODAY - timedelta(days=1)),
                   "Acme DC, Reno NV"))
    return [e for e in ev if e[1] <= TODAY]


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def main():
    orders, items = build()
    out = [
        "-- Acme Robotics orders (fictional). Generated by make_orders.py; do not edit.",
        f"-- 'Today' for every question about this data is {TODAY.isoformat()}.",
        # Read by the demo, so relative dates ("last week") resolve against
        # the data's own today rather than the visitor's clock.
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);",
        f"INSERT INTO meta VALUES ('today', '{TODAY.isoformat()}');",
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL,"
        " account_tier TEXT NOT NULL, email TEXT NOT NULL);",
        "CREATE TABLE products (sku TEXT PRIMARY KEY, model TEXT NOT NULL, unit_price INTEGER NOT NULL,"
        " lead_time_days INTEGER NOT NULL);",
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),"
        " placed_at TEXT NOT NULL, status TEXT NOT NULL, hold_reason TEXT, carrier TEXT, tracking_no TEXT,"
        " promised_by TEXT NOT NULL, shipped_at TEXT, delivered_at TEXT);",
        "CREATE TABLE order_items (order_id INTEGER NOT NULL REFERENCES orders(id), sku TEXT NOT NULL"
        " REFERENCES products(sku), qty INTEGER NOT NULL);",
        # seq is the event's place in the order's own timeline. Two events can
        # share a date (in transit and delivered the same day), and ORDER BY at
        # alone leaves their order undefined; seq makes it the lifecycle order.
        "CREATE TABLE shipments (order_id INTEGER NOT NULL REFERENCES orders(id), seq INTEGER NOT NULL,"
        " event TEXT NOT NULL, at TEXT NOT NULL, location TEXT NOT NULL, PRIMARY KEY (order_id, seq));",
    ]
    for cid, name, region, tier in CUSTOMERS:
        slug = "".join(ch for ch in name.lower() if ch.isalnum())[:18]
        out.append(f"INSERT INTO customers VALUES ({cid}, {q(name)}, {q(region)}, {q(tier)}, {q('ops@' + slug + '.example.com')});")
    for sku, model, price, lead in PRODUCTS:
        out.append(f"INSERT INTO products VALUES ({q(sku)}, {q(model)}, {price}, {lead});")
    for o in orders:
        cols = ["id", "customer_id", "placed_at", "status", "hold_reason", "carrier", "tracking_no",
                "promised_by", "shipped_at", "delivered_at"]
        out.append(f"INSERT INTO orders VALUES ({', '.join(q(o[c]) for c in cols)});")
    for oid, sku, qty in items:
        out.append(f"INSERT INTO order_items VALUES ({oid}, {q(sku)}, {qty});")
    for o in orders:
        for seq, (event, at, loc) in enumerate(shipments(o), start=1):
            out.append(f"INSERT INTO shipments VALUES ({o['id']}, {seq}, {q(event)}, {q(at)}, {q(loc)});")
    with open(OUT, "w") as f:
        f.write("\n".join(out) + "\n")
    print(f"Wrote {OUT}: {len(orders)} orders, {len(items)} items")


if __name__ == "__main__":
    main()
