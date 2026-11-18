"""Adversarial SQL corpus (eval/adversarial/sql_attacks.yaml).

The model writes the SQL, so any of these can arrive through a prompt
injection. Each case is either refused by the guard, or runs inside the
connection's hard limits and the role's views. The model is not involved:
the guarantees live in search/orders.py and SQLite, which is the point.
"""
import os
import time

import pytest
import yaml

from search import orders

CASES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "eval", "adversarial", "sql_attacks.yaml")
with open(CASES_PATH) as f:
    CASES = yaml.safe_load(f)


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    return orders.ensure_db(str(tmp_path_factory.mktemp("orders") / "orders.db"))


def run_as(db, role, sql):
    connection = orders.connect(db)
    try:
        orders.apply_role(connection, role)
        return orders.run(connection, orders.guard(sql))
    finally:
        connection.close()


@pytest.mark.parametrize("case", [c for c in CASES if c["expect"] == "reject"], ids=lambda c: c["id"])
def test_rejected_before_it_runs(case):
    with pytest.raises(orders.GuardError):
        orders.guard(case["sql"])


@pytest.mark.parametrize("case", [c for c in CASES if c["expect"] == "bounded"], ids=lambda c: c["id"])
def test_bounded_when_it_runs(db, case):
    started = time.monotonic()
    try:
        columns, rows = run_as(db, case.get("role", "admin"), case["sql"])
    except orders.GuardError:
        return  # refused at run time (budget or a hard limit): bounded
    finally:
        # Generous margin over the budget for a slow CI runner; the point is
        # "seconds", not "until the process is killed".
        assert time.monotonic() - started < orders.TIME_BUDGET_S * 3
    assert len(rows) <= orders.MAX_ROWS
    for row in rows:
        for value in row:
            if isinstance(value, (str, bytes)):
                assert len(value) <= orders.MAX_VALUE_BYTES


def test_contractor_only_ever_sees_west(db):
    _, rows = run_as(db, "contractor", "SELECT DISTINCT region FROM customers_v WHERE 1 = 1 OR region <> 'west'")
    assert {r[0] for r in rows} == {"west"}


def test_hidden_columns_are_null_for_the_role(db):
    _, rows = run_as(db, "contractor", "SELECT email FROM customers_v")
    assert rows and all(r[0] is None for r in rows)
    _, rows = run_as(db, "engineer", "SELECT unit_price FROM products_v")
    assert rows and all(r[0] is None for r in rows)


def test_the_connection_is_read_only(db):
    connection = orders.connect(db)
    try:
        with pytest.raises(Exception):
            connection.execute("DELETE FROM orders")
    finally:
        connection.close()


def test_every_case_has_a_known_expectation():
    assert {c["expect"] for c in CASES} <= {"reject", "bounded"}
    assert len({c["id"] for c in CASES}) == len(CASES)
