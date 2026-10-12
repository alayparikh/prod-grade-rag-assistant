import os
import time

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

import rag
from auth import smb
from indexer import crawl
from pipeline import health
from rag import HISTORY_TURNS, answer_question, build_chain, get_vectorstore
from search import metadata

load_dotenv()

# Per-session rate limit. In-memory and per-process - resets on restart and
# doesn't share state across multiple app instances. Fine for a single
# small-team deployment; a multi-instance rollout needs a shared store
# (Redis) instead.
RATE_LIMIT_MAX_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 3600

# Local demo mode (RAG_DEMO=1, see README "Try it locally"): synthetic corpus,
# offline answers, example questions.
DEMO = os.environ.get("RAG_DEMO") == "1"
DEMO_QUESTIONS = [
    "What is the deploy window?",
    "What is Sam Rivera's LinkedIn?",
    "Who is on the engineering team?",
    "What do I do in a SEV1 incident?",
]

st.set_page_config(page_title="Document Search", page_icon="📄", layout="centered")



# --- authentication -------------------------------------------------------
# The NAS validates the credentials and decides what they can see; this app
# keeps no user table. The password stays in session state for the life of
# the SMB session and is never written to disk or passed to any other
# function - auth.smb.login is the only thing that ever receives it.
def login_form():
    st.title("📄 Document Search")
    st.caption("Sign in with your NAS username and password.")

    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if not submitted:
        st.stop()

    try:
        session = smb.login(username, password)
    except smb.NasUnavailable as e:
        rag.log_event({"event": "login_error", "user": username, "error": str(e)})
        st.error("Can't reach the file server right now. Try again in a moment.")
        st.stop()

    if session is None:
        rag.log_event({"event": "login_failed", "user": username})
        st.error("Wrong username or password.")
        st.stop()

    rag.log_event({"event": "login", "user": username})
    st.session_state.nas_session = session
    st.rerun()


def current_session():
    if not smb.auth_enabled():
        return None  # local dev: RAG_AUTH_MODE=none, no login, no filtering

    session = st.session_state.get("nas_session")
    if session is None:
        login_form()
        st.stop()

    if session.expired():
        session.close()
        del st.session_state.nas_session
        st.warning("Signed out after inactivity. Please sign in again.")
        login_form()
        st.stop()

    session.touch()
    return session


nas_session = current_session()
user = nas_session.username if nas_session else "local"


# --- resources ------------------------------------------------------------
# The chain is shared across users: it is expensive to build and carries no
# per-user state. Authorization is applied per question instead, through
# the access check, so one cached chain cannot leak between users.
@st.cache_resource(show_spinner="Loading index...")
def load_chain():
    vectorstore = get_vectorstore()
    if vectorstore is None:
        return None
    over_fetch = rag.OVER_FETCH_MULTIPLIER if smb.auth_enabled() else 1
    return build_chain(vectorstore, over_fetch=over_fetch)


@st.cache_resource
def meta_db():
    if not os.path.exists(crawl.META_DB_PATH):
        return None
    # Cached for the life of the process and therefore read from whichever
    # script-runner thread Streamlit picks for a given rerun.
    return crawl.connect(shared_across_threads=True)


def access_checker():
    return smb.AccessChecker(nas_session) if nas_session else None


st.title("📄 Document Search")
if DEMO:
    st.info("**Live demo** over a fictional company's documents (handbook, "
            "runbooks, resumes, team roster). Offline mode: answers are the "
            "best-matching passages, found by hybrid search and a local "
            "reranker - no AI model is called.")

with st.sidebar:
    st.caption(f"Signed in as **{user}**")
    if nas_session and st.button("Sign out"):
        nas_session.close()
        del st.session_state.nas_session
        st.rerun()

    st.divider()
    mode = st.radio(
        "Mode",
        ["Ask about content", "Find a file"],
        help="Content search reads inside documents. File search matches "
             "names and folders, and covers files whose contents aren't "
             "indexed (images, drawings, archives).",
    )

    connection = meta_db()
    if connection is not None:
        total = connection.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
        st.caption(f"{total:,} files catalogued")
    st.caption("The index refreshes nightly.")
    if not rag.llm_enabled():
        st.info("Offline mode: answers are quoted passages from the documents. "
                "No AI model is called.")
    index_ok, index_message = health.check(rag.PERSIST_PATH)
    if not index_ok:
        st.warning(f"Answers may be out of date: {index_message}.")


# --- file search ----------------------------------------------------------
def render_file_search():
    connection = meta_db()
    if connection is None:
        st.warning("No file catalogue yet. Run `python -m indexer` on the server.")
        return

    question = st.text_input("What are you looking for?",
                             placeholder="the Diwali flyer from 2026")
    if not question:
        return

    started = time.time()
    query = metadata.parse_question(question)
    results = metadata.search_files(connection, query, access_check=access_checker())

    rag.log_event({
        "event": "find_file", "user": user, "mode": "find_file",
        "question_len": len(question), "terms": query.terms,
        "num_results": len(results),
        "latency_ms": round((time.time() - started) * 1000),
    })

    if not results:
        st.info("No matching files. Try a distinctive word from the file name.")
        return

    for row in results:
        st.markdown(f"**{row['name']}**")
        st.caption(f"{row['folder'] or '/'} · {crawl.human_bytes(row['size'])}")
        try:
            st.code(smb.nas_links(row["path"])["unc"], language=None)
        except ValueError:
            st.code(row["path"], language=None)  # local corpus, not on the NAS


# --- content chat ---------------------------------------------------------
def render_chat():
    chain = load_chain()
    if chain is None:
        st.warning("Nothing indexed yet. Run `python -m indexer` on the server.")
        return

    if "messages" not in st.session_state:
        st.session_state.messages = []  # [{"role", "content", "sources"}]
    if "request_times" not in st.session_state:
        st.session_state.request_times = []

    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            render_sources(msg.get("sources"))
            if msg["role"] == "assistant":
                render_feedback(i, msg)

    if DEMO and not st.session_state.messages:
        st.caption("Try one:")
        columns = st.columns(2)
        for i, example in enumerate(DEMO_QUESTIONS):
            if columns[i % 2].button(example, key=f"example_{i}", use_container_width=True):
                st.session_state.pending_question = example
                st.rerun()

    question = st.chat_input("Ask a question about your documents...")
    question = question or st.session_state.pop("pending_question", None)
    if not question:
        return

    now = time.time()
    st.session_state.request_times = [
        t for t in st.session_state.request_times if now - t < RATE_LIMIT_WINDOW_SECONDS
    ]

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    if len(st.session_state.request_times) >= RATE_LIMIT_MAX_REQUESTS:
        answer = (f"Rate limit reached ({RATE_LIMIT_MAX_REQUESTS} questions per "
                  f"hour). Please try again later.")
        sources = []
        with st.chat_message("assistant"):
            st.error(answer)
    else:
        st.session_state.request_times.append(now)

        chat_history = []
        for m in st.session_state.messages[:-1]:
            cls = HumanMessage if m["role"] == "user" else AIMessage
            chat_history.append(cls(content=m["content"]))
        chat_history = chat_history[-HISTORY_TURNS * 2:]

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("_Searching documents..._")
            response = answer_question(
                chain, question, chat_history,
                log_context={"user": user, "mode": "content"},
                access_check=access_checker(),
                user=user,
                on_token=lambda text: placeholder.markdown(text + " ▌"),
            )
            answer = response["answer"]
            sources = sorted(response["sources_used"])
            if response["guardrail"] and response["guardrail"].startswith("api_error"):
                placeholder.error(answer)
            else:
                placeholder.markdown(answer)
                render_sources(sources)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
        "question": question,
    })


# Citations are paths on the share, not names, so people can go open the
# file. Windows needs the UNC form; macOS and Linux open smb:// URLs.
def render_sources(sources):
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)})"):
        for source in sources:
            try:
                links = smb.nas_links(source)
            except ValueError:
                st.code(source, language=None)  # local dev corpus, not on the NAS
                continue
            st.code(links["unc"], language=None)
            st.caption(links["smb"])


def render_feedback(index, msg):
    if msg.get("rated"):
        st.caption("Thanks for the feedback.")
        return

    good, bad, _ = st.columns([1, 1, 8])
    for column, label, rating in ((good, "👍", "up"), (bad, "👎", "down")):
        if column.button(label, key=f"fb_{index}_{rating}"):
            rag.log_event({
                "event": "feedback", "user": user, "rating": rating,
                # Paths only, never answer text - this log is not
                # access-controlled and the corpus holds personal records.
                "sources_used": msg.get("sources", []),
                "question_len": len(msg.get("question", "")),
            })
            msg["rated"] = True
            st.rerun()


if mode == "Find a file":
    render_file_search()
else:
    render_chat()
