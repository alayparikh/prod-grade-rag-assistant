"""Question routing.

Three kinds of question reach this assistant, and answering them the same
way answers two of them badly:

  find_file   "where is the Diwali flyer" - wants a path, not a summary.
              Chunk retrieval is the wrong tool: the file may be an image
              with no indexed text at all.
  content     "what is our deploy window" - ordinary RAG.
  aggregate   "how many employees do we have" - needs a whole document,
              not the top-k chunks of it. Retrieval returns fragments of
              a roster, and counting rows across fragments is exactly
              where a confident wrong number comes from.

Routing is a Haiku call, cheap next to the Sonnet answer it steers. The
fallback when no LLM is configured is keyword-based and biased toward
"content", the mode that is never catastrophically wrong.
"""
import os
import re

from pydantic import BaseModel, Field

ROUTER_MODEL = os.environ.get("RAG_ROUTER_MODEL", "claude-haiku-4-5")

FIND_FILE = "find_file"
CONTENT = "content"
AGGREGATE = "aggregate"

_FIND_FILE_HINTS = re.compile(
    r"\b(where is|where are|find|locate|which folder|what folder|path to|"
    r"send me|give me the file|open the|link to)\b", re.I)
_AGGREGATE_HINTS = re.compile(
    r"\b(how many|how much|count|total|number of|list all|average|sum of)\b", re.I)
# "how many" questions that are answered from prose, not a register.
_AGGREGATE_EXCEPTIONS = re.compile(r"\b(how many days|how much time|how long)\b", re.I)


class Route(BaseModel):
    mode: str = Field(
        description=f"One of '{FIND_FILE}' (the user wants to locate a file), "
                    f"'{AGGREGATE}' (the user wants a count, total or "
                    f"complete list that must come from one authoritative "
                    f"document), or '{CONTENT}' (any other question about "
                    f"what documents say)."
    )
    subject: str | None = Field(
        default=None,
        description="For aggregate questions, the thing being counted or "
                    "listed, e.g. 'employees', 'open leave requests'. Null "
                    "otherwise.",
    )


def classify(question, llm=None):
    if llm is None:
        return _fallback_route(question)
    try:
        return llm.with_structured_output(Route).invoke(
            "Classify this request for a document assistant.\n\n"
            f"Request: {question}"
        )
    except Exception:  # noqa: BLE001 - routing must never fail the question
        return _fallback_route(question)


def _fallback_route(question):
    if _FIND_FILE_HINTS.search(question):
        return Route(mode=FIND_FILE)
    if _AGGREGATE_HINTS.search(question) and not _AGGREGATE_EXCEPTIONS.search(question):
        return Route(mode=AGGREGATE, subject=None)
    return Route(mode=CONTENT)


# Aggregate questions are answered from a named authoritative file rather
# than from retrieved fragments. The mapping is configuration, not
# inference: "the employee roster" is a fact about this organisation that
# the assistant cannot discover reliably, and guessing it wrong produces a
# confident wrong count.
def load_canonical_sources(path=None):
    import yaml

    path = path or os.environ.get("RAG_CANONICAL_SOURCES", "./canonical_sources.yaml")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return (yaml.safe_load(f) or {}).get("sources", {})


# Match the question's subject against the configured sources. Returns the
# path, or None when nothing is configured for it - in which case the
# caller falls back to ordinary retrieval rather than inventing a source.
def canonical_source_for(subject, sources):
    if not subject or not sources:
        return None
    needle = subject.lower().strip()
    for name, path in sources.items():
        key = name.lower()
        if key == needle or key in needle or needle in key:
            return path
    return None
