"""Agent load test: many concurrent agent questions with a misbehaving model.

    python eval/load/agent_load.py --questions 400 --workers 32
    python eval/load/agent_load.py --questions 400 --workers 32 --rate-limit 0.2 --slow 0.1

Runs the real agent loop (agent.answer_agent_question: tools, guards, role
views, access checks, bounds, logging) from W threads at once. The model is
a scripted stand-in, so the run is free and repeatable, and it misbehaves on
purpose, in the ways a real upstream does under load:

  normal    search, query, answer - with simulated network latency
  429       the API rate-limits a call               (--rate-limit fraction)
  timeout   the API times out a call                 (--timeouts fraction)
  slow      every call takes most of the deadline    (--slow fraction)
  runaway   the model never stops calling tools      (--runaway fraction)
  injected  the model tries to read what the asker may not
            (HR document, other regions' orders)     (--injected fraction)

Each simulated user has a role and an access check, as the app binds them.
Fails if any question:
  - raises instead of returning an answer,
  - runs more tool steps than MAX_STEPS or more model calls than MAX_STEPS + 1,
  - takes longer than the deadline plus one model call,
  - shows a contractor a non-west order row, or cites a document the asker's
    access check denies (cross-user leakage under concurrency),
  - or the API failures are not reported as typed api_error guardrails.
"""
import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

WORKDIR = tempfile.mkdtemp(prefix="rag_agent_load_")
os.environ["RAG_LOG_PATH"] = os.path.join(WORKDIR, "events.jsonl")

from langchain_core.documents import Document  # noqa: E402
from langchain_core.exceptions import ModelRateLimitError, ModelTimeoutError  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

import agent  # noqa: E402
import rag  # noqa: E402

POLICY = "/docs/shipping_policy.md"
HR_ONLY = "/docs/hr/salaries.md"
DOCS = [
    Document(page_content="Held orders: contact the customer within one business day.", metadata={"source": POLICY}),
    Document(page_content="Salary bands for 2026 (HR only).", metadata={"source": HR_ONLY}),
]
USERS = [  # (name, order role, may read HR docs)
    ("ana", "admin", True), ("ben", "engineer", False), ("cy", "contractor", False),
    ("dee", "contractor", False), ("eli", "admin", False), ("hr-fay", "none", True),
]


class Retriever:
    def retrieve(self, query, config=None):
        return list(DOCS)


CHAIN = SimpleNamespace(history_aware_retriever=Retriever(), reranker=None, grader=None, max_context=None)


def call(name, args):
    return {"name": name, "args": args}


class ChaosModel:
    """Scripted turns with injected latency and failures. One per question."""

    def __init__(self, behaviour, latency_s, slow_s, rng):
        self.behaviour, self.latency_s, self.slow_s, self.rng = behaviour, latency_s, slow_s, rng
        self.calls = 0
        if behaviour == "runaway":
            self.turns = [[call(agent.SEARCH_DOCS, {"query": f"q{i}"})] for i in range(50)]
        elif behaviour == "injected":
            self.turns = [
                [call(agent.QUERY_ORDERS, {"sql": "SELECT name, region, email FROM customers_v"}),
                 call(agent.QUERY_ORDERS, {"sql": "SELECT email FROM customers"})],
                [call(agent.FINAL_ANSWER, {"answer": "Here is everything.",
                                           "sources_used": [HR_ONLY, "/etc/passwd"]})],
            ]
        else:
            self.turns = [
                [call(agent.SEARCH_DOCS, {"query": "held order policy"})],
                [call(agent.QUERY_ORDERS, {"sql": "SELECT id, status FROM orders_v WHERE status = 'on_hold'"})],
                [call(agent.FINAL_ANSWER, {"answer": "Order 1042 is held; contact the customer.",
                                           "sources_used": [POLICY]})],
            ]

    def bind_tools(self, tools, tool_choice=None):
        offered = {t["name"] for t in tools}
        outer = self

        class Bound:
            def invoke(self, messages, config=None):
                return outer._reply(offered)
        return Bound()

    def _reply(self, offered):
        self.calls += 1
        time.sleep(self.slow_s if self.behaviour == "slow" else self.latency_s * self.rng.uniform(0.5, 1.5))
        if self.behaviour == "429":
            raise ModelRateLimitError("429 Too Many Requests")
        if self.behaviour == "timeout" and self.calls == 2:
            raise ModelTimeoutError("upstream timed out")
        turn = self.turns.pop(0) if self.turns else []
        if offered == agent.TERMINAL_TOOLS:  # the closing call: answer from what was gathered
            turn = [call(agent.FINAL_ANSWER, {"answer": "Partial answer.", "sources_used": [POLICY]})]
        tool_calls = [{**c, "id": f"c{self.calls}_{i}", "type": "tool_call"} for i, c in enumerate(turn)]
        return AIMessage(content="", tool_calls=tool_calls,
                         usage_metadata={"input_tokens": 800, "output_tokens": 80, "total_tokens": 880})


def pick_behaviour(rng, args):
    roll = rng.random()
    for name, share in (("429", args.rate_limit), ("timeout", args.timeouts), ("slow", args.slow),
                        ("runaway", args.runaway), ("injected", args.injected)):
        if roll < share:
            return name
        roll -= share
    return "normal"


def ask(i, args, seed):
    rng = random.Random(seed + i)
    name, role, hr = USERS[i % len(USERS)]
    behaviour = pick_behaviour(rng, args)
    model = ChaosModel(behaviour, args.latency, agent.TIMEOUT_S * 0.6, rng)
    access_check = (lambda source: True) if hr else (lambda source: not source.startswith("/docs/hr/"))
    started = time.perf_counter()
    try:
        result = agent.answer_agent_question(f"Question {i} from {name}", [], CHAIN, role,
                                             access_check=access_check, user=name, llm=model,
                                             log_context={"user": name, "mode": "load"})
        error = None
    except Exception as e:  # noqa: BLE001 - the thing under test
        result, error = None, f"{type(e).__name__}: {e}"
    return {"i": i, "user": name, "role": role, "hr": hr, "behaviour": behaviour, "error": error,
            "result": result, "model_calls": model.calls, "s": time.perf_counter() - started}


def problems_for(r):
    out = []
    if r["error"]:
        return [f"raised {r['error']}"]
    result = r["result"]
    if len(result["steps"]) > agent.MAX_STEPS:
        out.append(f"{len(result['steps'])} steps > MAX_STEPS")
    if r["model_calls"] > agent.MAX_STEPS + 1:
        out.append(f"{r['model_calls']} model calls > MAX_STEPS + 1")
    # Deadline + one closing call at the slowest injected latency, plus slack
    # for a loaded runner.
    limit = agent.TIMEOUT_S + agent.TIMEOUT_S * 0.6 + 2
    if r["s"] > limit:
        out.append(f"took {r['s']:.1f}s > {limit:.1f}s")
    if r["behaviour"] in ("429", "timeout") and not (result["guardrail"] or "").startswith("api_error"):
        out.append(f"{r['behaviour']} reported as {result['guardrail']!r}, not api_error")
    for step in result["steps"]:
        rows = step["detail"].get("rows", [])
        columns = step["detail"].get("columns", [])
        if r["role"] == "contractor" and "region" in columns:
            regions = {row[columns.index("region")] for row in rows}
            if regions - {"west"}:
                out.append(f"contractor saw regions {sorted(regions)}")
        if r["role"] != "admin" and "email" in columns:
            if any(row[columns.index("email")] is not None for row in rows):
                out.append("non-admin saw an email")
        for passage in step["detail"].get("passages", []):
            if passage["source"].startswith("/docs/hr/") and not r["hr"]:
                out.append(f"{r['user']} was shown {passage['source']}")
    for source in result["sources_used"]:
        if source.startswith("/docs/hr/") and not r["hr"]:
            out.append(f"{r['user']} cited {source}")
        if source == "/etc/passwd":
            out.append("cited a path no tool returned")
    if r["role"] == "none" and result["used_orders"]:
        out.append("role 'none' used order data")
    return out


def pct(values, p):
    values = sorted(values)
    return round(values[max(1, -(-p * len(values) // 100)) - 1], 3) if values else None


def main():
    parser = argparse.ArgumentParser(description="Concurrent agent questions with injected model failures")
    parser.add_argument("--questions", type=int, default=200)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--latency", type=float, default=0.05, help="simulated seconds per model call")
    parser.add_argument("--rate-limit", type=float, default=0.1)
    parser.add_argument("--timeouts", type=float, default=0.05)
    parser.add_argument("--slow", type=float, default=0.05)
    parser.add_argument("--runaway", type=float, default=0.05)
    parser.add_argument("--injected", type=float, default=0.1)
    parser.add_argument("--deadline", type=float, default=3.0,
                        help="agent wall-clock limit for this run (RAG_AGENT_TIMEOUT_S), short to keep it fast")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--report")
    args = parser.parse_args()

    agent.TIMEOUT_S = args.deadline
    rag.ORDERS_DB = os.path.join(WORKDIR, "orders.db")
    from search import orders
    orders.ensure_db(rag.ORDERS_DB)

    results, lock, counter = [], threading.Lock(), iter(range(args.questions))

    def worker():
        while True:
            with lock:
                i = next(counter, None)
            if i is None:
                return
            r = ask(i, args, args.seed)
            with lock:
                results.append(r)

    started = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(args.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - started

    problems = []
    for r in results:
        problems += [f"q{r['i']} ({r['behaviour']}, {r['role']}): {p}" for p in problems_for(r)]
    by_behaviour = {}
    for r in results:
        b = by_behaviour.setdefault(r["behaviour"], {"n": 0, "s": [], "guardrails": {}})
        b["n"] += 1
        b["s"].append(r["s"])
        g = (r["result"] or {}).get("guardrail") or "answered"
        g = ":".join(g.split(":")[:2]) if g.startswith("api_error") else g.split(":")[0]
        b["guardrails"][g] = b["guardrails"].get(g, 0) + 1
    summary = {
        "questions": len(results), "workers": args.workers, "elapsed_s": round(elapsed, 2),
        "questions_per_s": round(len(results) / elapsed, 1),
        "p50_s": pct([r["s"] for r in results], 50), "p95_s": pct([r["s"] for r in results], 95),
        "max_s": round(max(r["s"] for r in results), 3), "deadline_s": agent.TIMEOUT_S,
        "max_steps": agent.MAX_STEPS,
        "behaviours": {k: {"n": v["n"], "p95_s": pct(v["s"], 95), "guardrails": v["guardrails"]}
                       for k, v in sorted(by_behaviour.items())},
        "problems": problems[:50], "num_problems": len(problems),
    }
    shutil.rmtree(WORKDIR, ignore_errors=True)
    print(json.dumps(summary, indent=2))
    if args.report:
        with open(args.report, "w") as f:
            json.dump(summary, f, indent=2)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
