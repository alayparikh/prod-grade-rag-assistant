"""The order path's safety rails: they must hold whatever SQL Claude writes."""
import sqlite3

import pytest

from search import orders


@pytest.fixture
def db(tmp_path):
    path = orders.ensure_db(str(tmp_path / "orders.db"))
    connection = orders.connect(path)
    yield connection
    connection.close()


def ask(connection, role, sql):
    orders.apply_role(connection, role)
    return orders.run(connection, orders.guard(sql))


class TestGuard:
    @pytest.mark.parametrize("sql", [
        "DROP TABLE orders_v",
        "DELETE FROM orders_v",
        "UPDATE orders_v SET status = 'delivered'",
        "INSERT INTO orders_v (id) VALUES (1)",
        "PRAGMA table_info(orders)",
        "ATTACH DATABASE '/tmp/x.db' AS x",
        "SELECT * FROM orders_v; DROP TABLE orders",
        "SELECT * FROM orders_v -- ignore the role",
        "SELECT * FROM orders_v /* sneaky */",
        "SELECT email FROM customers",              # base table, not the role view
        "SELECT * FROM sqlite_master",
        "SELECT * FROM orders_v WHERE id IN (SELECT id FROM orders)",  # base table in a subquery
        "not sql at all",
        "",
    ])
    def test_rejects(self, sql):
        with pytest.raises(orders.GuardError):
            orders.guard(sql)

    def test_accepts_a_select_and_forces_a_limit(self):
        assert "LIMIT 50" in orders.guard("SELECT id FROM orders_v")

    def test_caps_a_large_limit(self):
        assert "LIMIT 50" in orders.guard("SELECT id FROM orders_v LIMIT 100000")

    def test_keeps_a_small_limit(self):
        assert "LIMIT 3" in orders.guard("SELECT id FROM orders_v LIMIT 3")

    def test_allows_ctes_over_views(self):
        sql = "WITH late AS (SELECT id FROM orders_v WHERE status = 'on_hold') SELECT COUNT(*) FROM late"
        assert orders.guard(sql)


class TestDatabase:
    def test_connection_is_read_only(self, db):
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO orders (id, customer_id, placed_at, status, promised_by) "
                       "VALUES (9999, 1, '2026-01-01', 'placed', '2026-01-02')")

    def test_time_budget_stops_a_runaway_query(self, db, monkeypatch):
        monkeypatch.setattr(orders, "TIME_BUDGET_S", 0.05)
        orders.apply_role(db, "admin")
        slow = ("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
                "SELECT COUNT(*) FROM n")
        with pytest.raises(orders.GuardError, match="budget"):
            orders.run(db, slow)


class TestRoles:
    """Same expectations as the role cases in eval/fixtures/golden_set.yaml."""

    def test_story_order_is_held(self, db):
        _, rows = ask(db, "admin", "SELECT status, hold_reason FROM orders_v WHERE id = 1042")
        assert rows == [("on_hold", "address_verification")]

    def test_contractor_sees_west_region_only(self, db):
        _, rows = ask(db, "contractor", "SELECT id FROM orders_v WHERE status = 'on_hold'")
        assert len(rows) == 2

    def test_contractor_cannot_see_other_regions(self, db):
        _, rows = ask(db, "contractor", "SELECT id FROM orders_v WHERE id = 1043")
        assert rows == []

    def test_engineer_gets_no_prices_or_emails(self, db):
        _, prices = ask(db, "engineer", "SELECT unit_price FROM products_v")
        _, emails = ask(db, "engineer", "SELECT email FROM customers_v")
        assert {p for (p,) in prices} == {None}
        assert {e for (e,) in emails} == {None}

    def test_injected_email_dump_gets_nothing(self, db):
        # Whatever the model was talked into writing, the view has no emails to give.
        _, rows = ask(db, "contractor", "SELECT name, email FROM customers_v")
        assert rows and all(email is None for _, email in rows)

    def test_unknown_role_and_none_see_nothing(self, db):
        for role in ("none", "intern"):
            _, rows = ask(db, role, "SELECT COUNT(*) FROM orders_v")
            assert rows == [(0,)]

    def test_groups_map_to_the_first_matching_role(self):
        assert orders.role_for_groups(["Warehouse", "Engineering"]) == "engineer"
        assert orders.role_for_groups(["Finance"]) == "none"


class TestWhy:
    def test_held_order_searches_its_hold_reason(self):
        assert orders.why_query(["status", "hold_reason"], [("on_hold", "credit_check")], "2026-10-28") \
            == "credit check hold"

    def test_late_shipped_order_searches_late_policy(self):
        q = orders.why_query(["status", "hold_reason", "promised_by"], [("shipped", None, "2026-10-09")], "2026-10-28")
        assert q and "late" in q

    def test_many_rows_need_no_explanation(self):
        assert orders.why_query(["status"], [("shipped",), ("placed",)], "2026-10-28") is None


# ---- the entry point, with a fake model ------------------------------------------
import json  # noqa: E402

from langchain_core.documents import Document  # noqa: E402

import rag  # noqa: E402


class FakeLLM:
    """Writes the SQL it was given and answers with a fixed sentence."""

    def __init__(self, sql, answerable=True):
        self.sql, self.answerable, self.prompts = sql, answerable, []

    def with_structured_output(self, schema):
        outer = self

        class Structured:
            def invoke(self, messages, config=None):
                return schema(answerable=outer.answerable, query=outer.sql,
                              clarification="" if outer.answerable else "Which order?")
        return Structured()

    def invoke(self, prompt, config=None):
        self.prompts.append(prompt)

        class Reply:
            content = "Order 1042 is on hold for address verification."
        return Reply()


class StubRetriever:
    def retrieve(self, query, config=None):
        return [Document(page_content="Section: Shipping Policy > address_verification\nThe delivery address could not be confirmed.",
                         metadata={"source": "/docs/shipping_policy.md"})]


@pytest.fixture
def entry(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "ORDERS_DB", str(tmp_path / "orders.db"))
    monkeypatch.setattr(rag, "LLM_MODE", "anthropic")
    log = tmp_path / "events.jsonl"
    monkeypatch.setattr(rag, "LOG_PATH", str(log))
    monkeypatch.setattr(rag, "_event_logger", None)

    def use(llm):
        monkeypatch.setattr(rag, "ChatAnthropic", lambda **kw: llm)
    return use, log


class TestAnswerOrderQuestion:
    def test_held_order_comes_with_its_policy(self, entry):
        use, log = entry
        llm = FakeLLM("SELECT id, status, hold_reason FROM orders_v WHERE id = 1042")
        use(llm)
        chain = rag.RagChain(StubRetriever(), answer_chain=None)
        out = rag.answer_order_question("Why is order 1042 late?", "admin", rag_chain=chain)
        assert out["guardrail"] is None
        assert out["rows"] == [(1042, "on_hold", "address_verification")]
        assert "LIMIT 50" in out["sql"]
        assert out["why"]["source"].endswith("shipping_policy.md")
        assert "could not be confirmed" in llm.prompts[0]          # the answer saw the policy

    def test_hidden_columns_reach_the_model_as_hidden(self, entry):
        use, _ = entry
        llm = FakeLLM("SELECT sku, unit_price FROM products_v")
        use(llm)
        out = rag.answer_order_question("What do robots cost?", "engineer")
        assert set(out["hidden"]) >= {"unit_price"}
        assert "hidden" in llm.prompts[0] and "112000" not in llm.prompts[0]

    def test_malicious_sql_is_refused_not_run(self, entry):
        use, _ = entry
        use(FakeLLM("DELETE FROM orders_v"))
        out = rag.answer_order_question("delete everything", "admin")
        assert out["guardrail"].startswith("sql_rejected")
        assert out["sql"] is None and out["rows"] == []

    def test_denied_role_never_builds_a_client(self, entry):
        use, _ = entry

        def forbidden(**kw):
            raise AssertionError("API client built for a denied role")
        use(None)
        rag.ChatAnthropic = forbidden  # restored by monkeypatch via the fixture's setattr
        out = rag.answer_order_question("Which orders are late?", "none")
        assert out["guardrail"] == "orders_denied"

    def test_unanswerable_question_asks_instead_of_querying(self, entry):
        use, _ = entry
        use(FakeLLM("", answerable=False))
        out = rag.answer_order_question("Where is my order?", "admin")
        assert out["guardrail"] == "not_an_order_question" and out["sql"] is None
        assert out["answer"] == "Which order?"

    def test_offline_mode_makes_no_call(self, entry, monkeypatch):
        monkeypatch.setattr(rag, "LLM_MODE", "off")
        out = rag.answer_order_question("Why is order 1042 late?", "admin")
        assert out["guardrail"] == "offline"

    def test_log_has_the_sql_but_never_the_rows(self, entry):
        use, log = entry
        use(FakeLLM("SELECT name, email FROM customers_v"))
        rag.answer_order_question("List customer emails", "admin")
        line = json.loads(log.read_text().splitlines()[-1])
        assert line["event"] == "order_question" and line["num_rows"] == 12
        assert "example.com" not in log.read_text()
