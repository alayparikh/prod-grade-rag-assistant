"""The agent: questions that need more than one step or more than one source.

rag.answer_question and rag.answer_order_question each answer in one shot.
"Which on-hold orders are past their promised date, and what does the
playbook say to do about each hold?" needs a query, then a search per hold
reason, then an answer from both. Here Claude chooses the steps:

    search_docs    retrieval + per-file access check + rerank + grade (rag._refine)
    query_orders   SQL through the guard, the role views and the read-only
                   connection (search/orders.py)
    find_file      file-name search (search/metadata.py)
    ask_user       ends the turn with a clarifying question
    final_answer   ends the turn with the answer and its sources

The tools are thin wrappers: every guard is the one the one-shot paths
already use, and it runs inside the tool, whatever the model asks for. The
asker's role and access check are bound into the Toolbox when it is built;
no tool takes identity as an argument, so the model cannot supply one.

Everything is bounded: tool calls (RAG_AGENT_MAX_STEPS), total tokens
(RAG_AGENT_TOKEN_BUDGET), wall clock (RAG_AGENT_TIMEOUT_S), and the size of
every tool result. When a bound is hit the model gets one last call that can
only answer or ask, so the user gets what the evidence so far supports.

Stateless: nothing survives the call. A clarifying question is returned as
the result; the user's reply arrives as the next question with the
transcript as chat_history.

Scale path: the answer cache is skipped here (an answer depends on the
orders data as well as the index version). When it is added, key it on
user + index version + an orders snapshot id, in the shared cache.
"""
import json
import os
import time
from dataclasses import dataclass, field

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

import rag
from pipeline import tracing
from pipeline.prompts import AGENT_SYSTEM_PROMPT
from search import metadata, orders

MAX_STEPS = int(os.environ.get("RAG_AGENT_MAX_STEPS", 6))
TOKEN_BUDGET = int(os.environ.get("RAG_AGENT_TOKEN_BUDGET", 60_000))
TIMEOUT_S = float(os.environ.get("RAG_AGENT_TIMEOUT_S", 60))
CALL_TIMEOUT_S = 30
CALL_MAX_RETRIES = 2
CALL_MAX_TOKENS = 2048
# Caps on what one tool call may put in the prompt. Rows are already capped
# by the SQL guard (orders.MAX_ROWS).
MAX_PASSAGES = 5
MAX_PASSAGE_CHARS = 1500
MAX_FILES = 10

SEARCH_DOCS = "search_docs"
QUERY_ORDERS = "query_orders"
FIND_FILE = "find_file"
ASK_USER = "ask_user"
FINAL_ANSWER = "final_answer"
TERMINAL_TOOLS = frozenset({ASK_USER, FINAL_ANSWER})

NO_PASSAGES = "No relevant passages found."
ORDERS_DENIED = "Your role has no access to order data."
BOUND_ANSWER = "I couldn't finish that within my limits. Try a narrower question."
OFFLINE_ANSWER = ("The agent needs the Claude API. Without it, use the document and "
                  "order modes, which answer offline.")
CLOSING_NOTE = ("You have reached your limit for this question. Do not gather anything "
                "more: answer now from the results you already have, and say what is missing.")

ORDERS_PROMPT = """- query_orders: run one SQLite SELECT against the orders database.

{facts}

One SELECT, no comments, no other tables.
"""
ORDERS_DENIED_PROMPT = ("- The asker has no access to order data. If the question needs it, "
                        "say so.\n")
FILES_PROMPT = ("- find_file: find files by words in their name or folder, for requests "
                "to locate a file rather than read one.\n")


def _tool(name, description, properties, required):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties, "required": required}}


TOOL_SPECS = {
    SEARCH_DOCS: _tool(
        SEARCH_DOCS, "Search the company's documents and return the most relevant passages.",
        {"query": {"type": "string", "description": "What to look for, as a short phrase or question."}},
        ["query"]),
    QUERY_ORDERS: _tool(
        QUERY_ORDERS, "Run one read-only SQLite SELECT over the order views and return the rows.",
        {"sql": {"type": "string", "description": "One SELECT over the *_v views."}},
        ["sql"]),
    FIND_FILE: _tool(
        FIND_FILE, "Find files by distinctive words in their name or folder path.",
        {"terms": {"type": "array", "items": {"type": "string"},
                   "description": "Distinctive words likely to be in the file name or folder."},
         "year": {"type": "integer", "description": "Four-digit year the file relates to, if named."}},
        ["terms"]),
    ASK_USER: _tool(
        ASK_USER, "Ask the user one clarifying question and stop.",
        {"question": {"type": "string"}}, ["question"]),
    FINAL_ANSWER: _tool(
        FINAL_ANSWER, "Give the final answer and stop.",
        {"answer": {"type": "string"},
         "sources_used": {"type": "array", "items": {"type": "string"},
                          "description": "Exact 'Source: <path>' values relied on. Empty if none."}},
        ["answer"]),
}


@dataclass
class ToolResult:
    """What one tool call produced. `text` goes back to the model; `detail`
    is for the UI trace and is never logged (it holds rows and passages)."""
    text: str
    ok: bool = True
    count: int = 0
    detail: dict = field(default_factory=dict)


def _failed(message):
    return ToolResult(text=message, ok=False, detail={"error": message})


class Toolbox:
    """The tools for one question, with the asker's identity bound in."""

    def __init__(self, rag_chain, role, access_check, connection, order_access,
                 file_index=None, timer=None, config=None):
        self.rag_chain = rag_chain
        self.role = role
        self.access_check = access_check
        self.connection = connection
        self.order_access = order_access
        self.file_index = file_index
        self.timer = timer or tracing.StepTimer()
        self.config = config
        # What the tools actually returned: the only things an answer may cite.
        self.doc_sources = set()
        self.file_paths = set()
        self.has_evidence = False
        self.used_orders = False
        self.dropped_by_acl = 0
        self.started = time.perf_counter()
        self._seen = set()

    def specs(self):
        names = [SEARCH_DOCS]
        if not self.order_access["denied"]:
            names.append(QUERY_ORDERS)
        if self.file_index is not None:
            names.append(FIND_FILE)
        return [TOOL_SPECS[n] for n in (*names, ASK_USER, FINAL_ANSWER)]

    def run(self, name, args):
        handler = {SEARCH_DOCS: self._search_docs, QUERY_ORDERS: self._query_orders,
                   FIND_FILE: self._find_file}.get(name)
        if handler is None:
            return _failed(f"Unknown tool {name!r}.")
        # A model stuck repeating a call would otherwise burn every step on it.
        key = (name, json.dumps(args, sort_keys=True, default=str))
        if key in self._seen:
            return _failed("You already made this exact call. Use the earlier result.")
        self._seen.add(key)
        return handler(args if isinstance(args, dict) else {})

    def _search_docs(self, args):
        query = str(args.get("query") or "").strip()
        if not query:
            return _failed("search_docs needs a query.")
        if self.rag_chain is None:
            return _failed("Document search is not available.")
        retriever = self.rag_chain.history_aware_retriever
        with self.timer.step("retrieve"):
            docs = (retriever.retrieve(query, self.config) if hasattr(retriever, "retrieve")
                    else retriever.invoke({"input": query, "chat_history": []}))
        acl_stats = {"num_dropped_by_acl": 0}
        # Access check, rerank and grade: the same stages, in the same order,
        # as the one-shot path. Text the asker cannot open stops here.
        docs = rag._refine(self.rag_chain, query, docs, self.access_check, acl_stats,
                           self.timer, self.config) or []
        self.dropped_by_acl += acl_stats["num_dropped_by_acl"]
        passages = [{"source": d.metadata.get("source", "?"), "text": d.page_content[:MAX_PASSAGE_CHARS]}
                    for d in docs[:MAX_PASSAGES]]
        if not passages:
            # The same words whether nothing matched or the asker may not read
            # what did, so the reply cannot be used to probe for a file.
            return ToolResult(text=NO_PASSAGES, detail={"passages": []})
        self.doc_sources.update(p["source"] for p in passages)
        self.has_evidence = True
        body = "\n\n".join(f"Source: {p['source']}\n{p['text']}" for p in passages)
        return ToolResult(text=f"<retrieved_context>\n{body}\n</retrieved_context>",
                          count=len(passages), detail={"passages": passages})

    def _query_orders(self, args):
        if self.order_access["denied"]:
            return _failed(ORDERS_DENIED)
        try:
            sql = orders.guard(str(args.get("sql") or ""))
            with self.timer.step("sql_run"):
                columns, rows = orders.run(self.connection, sql)
        except orders.GuardError as e:
            return _failed(f"Query rejected: {e}")
        hidden = set(self.order_access["hidden"])
        if "unit_price" in hidden:
            hidden.add("line_total")
        self.has_evidence = True
        self.used_orders = True
        table = rag._rows_as_text(columns, rows, hidden)
        return ToolResult(
            text=f"<query_result rows=\"{len(rows)}\">\n{table}\n</query_result>", count=len(rows),
            detail={"sql": sql, "columns": columns, "rows": [list(r) for r in rows],
                    "hidden": sorted(hidden & set(columns))})

    def _find_file(self, args):
        if self.file_index is None:
            return _failed("File search is not available.")
        terms = [str(t) for t in args.get("terms") or []]
        year = args.get("year") if isinstance(args.get("year"), int) else None
        query = metadata.FileQuery(terms=terms, year=year)
        with self.timer.step("find_file"):
            found = metadata.search_files(self.file_index, query, limit=MAX_FILES,
                                          access_check=self.access_check)
        files = [{"path": row["path"], "name": row["name"]} for row in found]
        if not files:
            return ToolResult(text="No matching files.", detail={"files": []})
        self.file_paths.update(f["path"] for f in files)
        self.has_evidence = True
        listing = "\n".join(f"Source: {f['path']}" for f in files)
        return ToolResult(text=f"<files>\n{listing}\n</files>", count=len(files), detail={"files": files})


def _system_prompt(connection, order_access, file_index):
    order_text = (ORDERS_DENIED_PROMPT if order_access["denied"]
                  else ORDERS_PROMPT.format(facts=orders.schema_facts(connection)))
    return AGENT_SYSTEM_PROMPT.format(
        max_steps=MAX_STEPS, orders=order_text,
        files=FILES_PROMPT if file_index is not None else "")


def _total_tokens(message):
    usage = getattr(message, "usage_metadata", None) or {}
    return usage.get("total_tokens") or usage.get("input_tokens", 0) + usage.get("output_tokens", 0)


def _bound_hit(num_steps, tokens, deadline):
    if num_steps >= MAX_STEPS:
        return "step_cap"
    if tokens >= TOKEN_BUDGET:
        return "budget"
    if time.monotonic() >= deadline:
        return "timeout"
    return None


def _sole_terminal(calls):
    """The ask_user / final_answer call, if it is the only call of the turn.
    One sent alongside other calls was written before their results existed,
    so it is not an answer to anything yet."""
    if len(calls) == 1 and calls[0]["name"] in TERMINAL_TOOLS:
        return calls[0]
    return None


def _execute(call, toolbox, steps, on_step):
    """Run one tool call and return the message that reports it to the model."""
    name, args = call["name"], call.get("args") or {}
    if name in TERMINAL_TOOLS:
        text = "Call this on its own, after you have read the other results."
    elif len(steps) >= MAX_STEPS:
        text = "Not run: the tool-call limit for this question is reached."
    else:
        started = time.perf_counter()
        result = toolbox.run(name, args)
        finished = time.perf_counter()
        # at_ms: when the step finished, measured from the start of the question.
        step = {"tool": name, "args": args, "ok": result.ok, "count": result.count,
                "ms": round((finished - started) * 1000),
                "at_ms": round((finished - toolbox.started) * 1000), "detail": result.detail}
        steps.append(step)
        if on_step is not None:
            on_step(step)
        text = result.text
    return ToolMessage(content=text, tool_call_id=call["id"])


def _run_loop(llm, toolbox, messages, steps, on_step, deadline, config):
    """Returns (terminal tool call or None, the bound that was hit or None).
    At most MAX_STEPS + 1 model calls: the working turns, then one closing
    call that is only offered ask_user and final_answer."""
    specs = toolbox.specs()
    working = llm.bind_tools(specs, tool_choice="any")
    closing = llm.bind_tools([s for s in specs if s["name"] in TERMINAL_TOOLS], tool_choice="any")
    tokens = 0
    for _ in range(MAX_STEPS + 1):
        bound = _bound_hit(len(steps), tokens, deadline)
        if bound:
            messages.append(HumanMessage(content=CLOSING_NOTE))
        reply = tracing.invoke(closing if bound else working, messages, config)
        tokens += _total_tokens(reply)
        messages.append(reply)
        calls = getattr(reply, "tool_calls", None) or []
        terminal = _sole_terminal(calls)
        if terminal is not None:
            return terminal, bound
        if bound or not calls:
            return None, bound or "no_tool_call"
        messages.extend(_execute(call, toolbox, steps, on_step) for call in calls)
    return None, "step_cap"


def _resolve(terminal, bound, toolbox):
    """Turn the loop's outcome into (answer, sources_used, clarification, guardrail)."""
    if terminal is None:
        return BOUND_ANSWER, [], False, bound
    args = terminal.get("args") or {}
    if terminal["name"] == ASK_USER:
        question, _ = rag.redact_secrets(str(args.get("question") or "").strip())
        return question or "Could you give me more detail?", [], True, "clarification"

    answer = str(args.get("answer") or "").strip()
    # No tool returned anything, so whatever the model wrote is ungrounded.
    if not toolbox.has_evidence or not answer:
        return rag.NO_CONTEXT_ANSWER, [], False, "no_evidence"
    # A path the model names that no tool returned is dropped, not trusted.
    citable = toolbox.doc_sources | toolbox.file_paths
    sources = [s for s in args.get("sources_used") or [] if s in citable]
    answer, redacted = rag.redact_secrets(answer)
    return answer, sources, False, "secret_redacted" if redacted else bound


def _loggable(step):
    # Tool, timing and counts, plus the SQL (as the order path logs it). Never
    # rows, passages or search text: this log is not access-controlled.
    entry = {k: step[k] for k in ("tool", "ms", "ok", "count")}
    if step["detail"].get("sql"):
        entry["sql"] = step["detail"]["sql"]
    return entry


def answer_agent_question(question, chat_history, rag_chain, role, access_check=None,
                          user=None, log_context=None, on_step=None, file_index=None, llm=None):
    """Answer one question with the agent loop.

    role and access_check are the asker's identity, from the caller's
    session; they are never read from the model. on_step, when given,
    receives each step as it finishes. llm is injectable for tests.

    Returns {"answer", "sources_used", "used_orders", "steps",
    "clarification", "guardrail", "usage", "latency_ms"}. Each step is
    {"tool", "args", "ok", "count", "ms", "at_ms", "detail"}: the one trace
    format the Streamlit UI renders and the demo page replays.
    """
    start = time.time()
    log_context = log_context or {}
    timer = tracing.StepTimer()
    steps = []
    out = {"answer": "", "sources_used": [], "used_orders": False, "steps": steps,
           "clarification": False, "guardrail": None}

    def finish(guardrail, usage=None, **fields):
        # No usage means no model call happened, which is genuinely free.
        usage = usage or {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "models_called": []}
        latency_ms = round((time.time() - start) * 1000)
        out.update(fields, guardrail=guardrail, usage=usage, latency_ms=latency_ms)
        rag.log_event({
            "event": "agent_question", "question_len": len(question), "role": role,
            "num_steps": len(steps), "steps": [_loggable(s) for s in steps],
            "num_sources_used": len(out["sources_used"]), "sources_used": sorted(out["sources_used"]),
            "guardrail": guardrail, **timer.steps, "latency_ms": latency_ms,
            **usage, **log_context,
        })
        return out

    if len(question) > rag.MAX_QUESTION_LENGTH:
        return finish("input_too_long", answer=f"Question is too long ({len(question)} characters, "
                                               f"max {rag.MAX_QUESTION_LENGTH}).")
    if llm is None and not rag.llm_enabled():
        return finish("offline", answer=OFFLINE_ANSWER)

    connection = orders.connect(orders.ensure_db(rag.ORDERS_DB))
    try:
        order_access = orders.apply_role(connection, role)
        config = tracing.run_config(user=user or log_context.get("user"), tags=["agent"])
        toolbox = Toolbox(rag_chain, role, access_check, connection, order_access,
                          file_index=file_index, timer=timer, config=config)
        llm = llm or ChatAnthropic(model=rag.MODEL, max_tokens=CALL_MAX_TOKENS,
                                   timeout=CALL_TIMEOUT_S, max_retries=CALL_MAX_RETRIES)
        messages = [SystemMessage(content=_system_prompt(connection, order_access, file_index)),
                    *chat_history, HumanMessage(content=question)]
        with get_usage_metadata_callback() as usage_cb:
            try:
                with timer.step("agent"):
                    terminal, bound = _run_loop(llm, toolbox, messages, steps, on_step,
                                                time.monotonic() + TIMEOUT_S, config)
            except rag._API_ERRORS as e:
                message, tag = rag._api_error_message(e)
                return finish(tag, rag.summarize_usage(usage_cb.usage_metadata), answer=message)
            usage = rag.summarize_usage(usage_cb.usage_metadata)
        answer, sources, clarification, guardrail = _resolve(terminal, bound, toolbox)
        return finish(guardrail, usage, answer=answer, sources_used=sources,
                      used_orders=toolbox.used_orders, clarification=clarification)
    finally:
        connection.close()
