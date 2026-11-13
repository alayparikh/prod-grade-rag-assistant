"""Build the agent runs the demo page plays back: demo/web/agent.json.

The demo page is static and calls no AI service, so it cannot run the agent
(agent.py). This runs each demo question once per role over the fixture
corpus and orders database and saves what happened - every step, what each
step read, the answer - for the page to replay.

    python demo/agent_runs.py            # example runs; no API call, no cost
    python demo/agent_runs.py --live     # the real agent; calls Claude, costs money
    python demo/agent_runs.py --check    # no API call: is agent.json current?

Example runs (the default) go through the real agent loop with the model
replaced by a script (demo/agent_examples.yaml). The tools are the real ones:
SQL through the guard and the role's views, searches through real retrieval
and the role's document access. So each step and what it returned is real;
which steps to take and the answer's wording are scripted. The file says
which kind it holds (`kind`), and the page labels the runs accordingly.

--live swaps the script for Claude. It has not been run yet: treat its first
run as a test of that path, not as a known-good command.

Nothing unchecked is written. For every run: the agent's own checks must
leave the scripted answer and its citations unchanged (an answer with no
evidence, or a cited file the steps never returned, fails the build), the
run is scanned for anything its role may not see, and the Admin run must
meet the question's expectations in eval/fixtures/golden_set.yaml.

--check is what CI runs. The file stores a fingerprint of everything that
shaped it (fixtures, prompts, tool definitions, model, questions, roles, the
example script) and the check recomputes it, so a change to any of them
fails the deploy until the runs are rebuilt.

The questions are the `mode: agent`, `demo: true` cases of the golden set, so
the page and the live eval ask the same things.
"""
import argparse
import datetime
import hashlib
import inspect
import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "eval"))

DOCS = os.path.join(ROOT, "eval", "fixtures", "docs")
ORDERS_SQL = os.path.join(ROOT, "eval", "fixtures", "orders.sql")
GOLDEN = os.path.join(ROOT, "eval", "fixtures", "golden_set.yaml")
EXAMPLES = os.path.join(ROOT, "demo", "agent_examples.yaml")
OUT = os.path.join(ROOT, "demo", "web", "agent.json")
LIVE = "--live" in sys.argv
LIVE_ATTEMPTS = 3

# rag reads its settings at import. Point it at the fixtures and a throwaway
# index so a build never touches (or depends on) a developer's real one, and
# switch the model off unless this is a --live run, so that the default
# build cannot construct an API client at all.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
_WORK = tempfile.mkdtemp(prefix="agent_runs_")
os.environ.update({
    "RAG_DOCS_PATH": DOCS, "RAG_PERSIST_PATH": _WORK,
    "RAG_LOG_PATH": os.path.join(_WORK, "events.jsonl"),
    "RAG_META_DB": os.path.join(_WORK, "meta.sqlite"),
})
if not LIVE:
    os.environ["RAG_LLM"] = "off"

import yaml  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

import agent  # noqa: E402
import rag  # noqa: E402
from pipeline import chunking, prompts  # noqa: E402
from search import orders  # noqa: E402
from run_eval import check_agent_result  # noqa: E402

# Which documents each demo role can open. Mirrors ROLES in demo/web/roles.js;
# the file lists are written into agent.json and demo/check_search.mjs fails
# if the page's rules give a different list.
_GENERAL = {"team_roster.md", "company_handbook.md", "onboarding_guide.md", "security_policy.md"}
_WAREHOUSE = {"company_handbook.md", "onboarding_guide.md", "testing_standards.md",
              "order_lifecycle.md", "shipping_policy.md", "product_catalog.md"}
DOC_RULES = {
    "admin": lambda name: True,
    "engineer": lambda name: "_resume." not in name,
    "hr": lambda name: "_resume." in name or name in _GENERAL,
    "contractor": lambda name: name in _WAREHOUSE,
}
# The demo's HR role has no order role, so it is passed through as-is and
# search/orders.py treats the unknown role as no access.
ROLES = list(DOC_RULES)


def doc_files():
    return sorted(name for name in os.listdir(DOCS) if not name.startswith("."))


def readable_files(role):
    return [name for name in doc_files() if DOC_RULES[role](name)]


def demo_items():
    with open(GOLDEN) as f:
        return [item for item in yaml.safe_load(f) if item.get("mode") == "agent" and item.get("demo")]


def load_examples():
    with open(EXAMPLES) as f:
        return yaml.safe_load(f)


def fingerprint(items):
    """Hash of everything that shapes the runs. Retrieval code is covered only
    through CHUNKER_VERSION; a change to ranking that leaves the version alone
    will not be noticed here, and the page's own search check is what catches it."""
    digest = hashlib.sha256()

    def feed(label, data):
        digest.update(label.encode() + b"\0" + (data if isinstance(data, bytes) else data.encode()) + b"\0")

    for name in doc_files():
        with open(os.path.join(DOCS, name), "rb") as f:
            feed(name, f.read())
    for label, path in (("orders.sql", ORDERS_SQL), ("examples", EXAMPLES)):
        with open(path, "rb") as f:
            feed(label, f.read())
    feed("prompts", prompts.AGENT_SYSTEM_PROMPT + agent.ORDERS_PROMPT + agent.ORDERS_DENIED_PROMPT
         + agent.FILES_PROMPT + agent.CLOSING_NOTE)
    feed("tools", json.dumps(agent.TOOL_SPECS, sort_keys=True))
    # The schema facts are part of the agent's prompt.
    feed("schema", inspect.getsource(orders.schema_facts))
    feed("model", rag.MODEL)
    feed("limits", f"{agent.MAX_STEPS}/{agent.MAX_PASSAGES}/{agent.MAX_PASSAGE_CHARS}/{chunking.CHUNKER_VERSION}")
    feed("questions", json.dumps([[item["id"], item["question"]] for item in items]))
    feed("roles", json.dumps({role: readable_files(role) for role in ROLES}))
    return digest.hexdigest()


def order_facts():
    """What the leak scan looks for: values only some roles may see."""
    connection = sqlite3.connect(":memory:")
    try:
        with open(ORDERS_SQL) as f:
            connection.executescript(f.read())
        emails = [row[0] for row in connection.execute("SELECT email FROM customers")]
        outside_west = [row[0] for row in connection.execute("SELECT name FROM customers WHERE region != 'west'")]
    finally:
        connection.close()
    return {"emails": emails, "outside_west": outside_west}


def leaks(role, run, facts):
    """Problems that make a run unpublishable for `role`. Empty means clean."""
    problems = []
    readable = set(readable_files(role))
    text = json.dumps(run)
    for step in run["steps"]:
        detail = step["detail"]
        for passage in detail.get("passages", []):
            if passage["source"] not in readable:
                problems.append(f"read {passage['source']}, which {role} cannot open")
        hidden_at = [detail["columns"].index(c) for c in detail.get("hidden", [])]
        if any(row[i] is not None for row in detail.get("rows", []) for i in hidden_at):
            problems.append(f"a hidden column has a value in: {detail['sql']}")
        if role == "hr" and step["tool"] == agent.QUERY_ORDERS and step["ok"]:
            problems.append("queried orders, which hr has no access to")
    problems += [f"cites {source}, which {role} cannot open" for source in run["sources"] if source not in readable]
    if role != "admin":
        problems += [f"contains the email {email}" for email in facts["emails"] if email in text]
    if role == "contractor":
        problems += [f"names {name}, a customer outside the West region"
                     for name in facts["outside_west"] if name in text]
    return problems


# ---- example runs: the model replaced by a script ----------------------------
class ScriptedModel:
    """Stands in for Claude: plays back the tool calls of one example, turn by
    turn, then the scripted answer. Everything the calls do is still done by
    the real tools."""

    def __init__(self, turns):
        self.turns = list(turns)

    def bind_tools(self, tools, tool_choice=None):
        return self

    def invoke(self, messages, config=None):
        calls = self.turns.pop(0) if self.turns else []
        return AIMessage(content="", tool_calls=[
            {"name": name, "args": args, "id": f"example_{len(self.turns)}_{i}", "type": "tool_call"}
            for i, (name, args) in enumerate(calls)])


class CutoffReranker:
    """With no model to grade relevance, a passage has to clear the reranker
    score the page's own search requires (rag.OFFLINE_MIN_SCORE), so an
    example never shows a passage the page itself would call unrelated."""

    def __init__(self, reranker):
        self.reranker = reranker

    def rerank(self, query, docs):
        return [d for d in self.reranker.rerank(query, docs)
                if d.metadata.get("rerank_score", rag.OFFLINE_MIN_SCORE) >= rag.OFFLINE_MIN_SCORE]


def scripted_turns(example, role):
    if "ask" in example:
        return [[(agent.ASK_USER, {"question": example["ask"]})]], example["ask"], []
    plan = example["plans"].get(role, example["plans"]["default"])
    turns = [[(call["tool"], {k: v for k, v in call.items() if k != "tool"}) for call in turn] for turn in plan]
    answer = example["answers"][role]
    turns.append([(agent.FINAL_ANSWER, {"answer": answer["text"], "sources_used": answer["sources"]})])
    return turns, answer["text"], sorted(answer["sources"])


def _public_passage(passage):
    section, _, body = passage["text"].partition("\n")
    labelled = section.startswith("Section: ")
    return {"source": os.path.basename(passage["source"]),
            "section": section[len("Section: "):] if labelled else "",
            "text": body if labelled else passage["text"]}


def public_run(result):
    """The result as the page shows it: file names instead of paths."""
    steps = []
    for step in result["steps"]:
        detail = dict(step["detail"])
        if "passages" in detail:
            detail["passages"] = [_public_passage(p) for p in detail["passages"]]
        steps.append({**step, "detail": detail})
    return {
        "answer": result["answer"].replace(DOCS + os.sep, ""),
        "sources": sorted(os.path.basename(s) for s in result["sources_used"]),
        "used_orders": result["used_orders"], "clarification": result["clarification"],
        "guardrail": result["guardrail"], "steps": steps,
        "latency_ms": result["latency_ms"], "cost_usd": result["usage"]["cost_usd"],
    }


def run_agent(item, role, chain, llm=None):
    readable = set(readable_files(role))

    def can_open(path):
        return os.path.basename(path) in readable

    def cite(name):
        # The script cites file names; the agent validates full paths.
        return os.path.join(DOCS, name)

    if llm is not None:
        for turn in llm.turns:
            for name, args in turn:
                if name == agent.FINAL_ANSWER:
                    args["sources_used"] = [cite(s) for s in args["sources_used"]]
    return agent.answer_agent_question(item["question"], [], chain, role, access_check=can_open,
                                       log_context={"mode": "demo-runs"}, llm=llm)


def example_run(item, role, chain, example):
    turns, text, sources = scripted_turns(example, role)
    result = run_agent(item, role, chain, llm=ScriptedModel(turns))
    run = public_run(result)
    # The agent replaces an answer with nothing behind it and drops a citation
    # its steps never returned. If either happened, the script claims more
    # than this role's steps support.
    if run["answer"].strip() != text.strip():
        raise SystemExit(f"{item['id']} as {role}: the scripted answer has no evidence behind it; "
                         f"the agent would say: {run['answer']!r}")
    if run["sources"] != sources:
        raise SystemExit(f"{item['id']} as {role}: scripted sources {sources}, but the steps support {run['sources']}")
    return result, run


def live_run(item, role, chain):
    for attempt in range(1, LIVE_ATTEMPTS + 1):
        result = run_agent(item, role, chain)
        if (result["guardrail"] or "").startswith("api_error"):
            raise SystemExit(f"{item['id']} as {role}: {result['guardrail']}")
        # Expectations are written for a reader who can see everything.
        ok, reason = check_agent_result(item, result) if role == "admin" else (True, "")
        if ok:
            return result, public_run(result)
        print(f"  {role:<10} attempt {attempt} missed its expectations: {reason}")
    raise SystemExit(f"{item['id']} as {role}: expectations not met in {LIVE_ATTEMPTS} attempts")


def build(live):
    if live and not rag.llm_enabled():
        print("--live calls Claude: set ANTHROPIC_API_KEY (and RAG_LLM=auto).")
        return 1
    items = demo_items()
    examples = load_examples()
    vectorstore = rag.get_vectorstore()
    if vectorstore is None:
        print(f"No documents found in {DOCS}.")
        return 1
    # No answer cache and a fresh index: the runs must come from this build.
    chain = rag.build_chain(vectorstore, use_cache=False)
    if not live:
        chain.reranker = CutoffReranker(chain.reranker)
    facts = order_facts()

    questions = []
    for item in items:
        print(item["question"])
        runs = {}
        for role in ROLES:
            result, run = live_run(item, role, chain) if live else example_run(item, role, chain, examples[item["id"]])
            problems = leaks(role, run, facts)
            if problems:
                raise SystemExit(f"{item['id']} as {role} is not publishable: {'; '.join(problems)}")
            if role == "admin":
                ok, reason = check_agent_result(item, result)
                if not ok:
                    raise SystemExit(f"{item['id']} as admin misses its expectations: {reason}")
            print(f"  {role:<10} {len(run['steps'])} steps · {'asked back' if run['clarification'] else run['guardrail'] or 'answered'}")
            runs[role] = run
        questions.append({"id": item["id"], "question": item["question"], "runs": runs})

    costs = [run["cost_usd"] for q in questions for run in q["runs"].values()]
    payload = {
        "kind": "recorded" if live else "example",
        "made_at": datetime.date.today().isoformat(),
        "model": rag.MODEL if live else None,
        "cost_usd": (None if None in costs else round(sum(costs), 4)) if live else None,
        "fingerprint": fingerprint(items),
        "roles": {role: {"files": readable_files(role)} for role in ROLES},
        "questions": questions,
    }
    partial = OUT + ".partial"
    with open(partial, "w") as f:
        json.dump(payload, f, indent=1)
    os.replace(partial, OUT)
    print(f"\nWrote {OUT}: {len(questions)} questions x {len(ROLES)} roles ({payload['kind']} runs).")
    return 0


def check():
    """No API call. Fails when agent.json is missing, incomplete, stale, or
    holds something a role may not see."""
    if not os.path.exists(OUT):
        print(f"{OUT} is missing. Build it: python demo/agent_runs.py")
        return 1
    with open(OUT) as f:
        payload = json.load(f)
    items = demo_items()
    problems = []
    if payload["fingerprint"] != fingerprint(items):
        problems.append("the fixtures, prompts, tools, model, questions, roles or example script changed since it was built")
    built = {q["id"]: q for q in payload["questions"]}
    facts = order_facts()
    for item in items:
        runs = built.get(item["id"], {}).get("runs", {})
        for role in ROLES:
            if role not in runs:
                problems.append(f"{item['id']} has no run as {role}")
                continue
            problems += [f"{item['id']} as {role}: {p}" for p in leaks(role, runs[role], facts)]
    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        print("\nBuild it again: python demo/agent_runs.py")
        return 1
    print(f"agent.json is current: {len(items)} questions x {len(ROLES)} roles, {payload['kind']} runs made {payload['made_at']}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Build the agent runs the demo page plays back")
    parser.add_argument("--live", action="store_true",
                        help="run the real agent instead of the example script (calls Claude; costs money)")
    parser.add_argument("--check", action="store_true",
                        help="check the existing agent.json instead of building it (no API call)")
    args = parser.parse_args()
    return check() if args.check else build(args.live)


if __name__ == "__main__":
    sys.exit(main())
