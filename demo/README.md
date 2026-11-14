# In-browser demo

A static page that searches a fictional company's documents (Acme Robotics)
entirely in the visitor's browser. No server, no API key, nothing billable.

Live: https://alayparikh.github.io/prod-grade-rag-assistant/

## How it is split

The pipeline has two halves, and they run in different places.

| Half | Runs | Code |
|---|---|---|
| **Ingest**: load files, chunk at headings, embed | Python, in CI, once per deploy | `demo/build_index.py` calls `rag.load_file`, `pipeline/chunking.py` and the real embedding model |
| **Query**: embed question, two searches, fuse, rerank, threshold | JavaScript, in the browser, per question | `demo/web/search.js` |

The hand-off is `demo/web/index.json`: every chunk's text, source file,
section and 384-number embedding, plus the pipeline's constants (k, fusion
constant, rerank top-N, score cutoff) read from the Python source so the two
halves never hold different numbers.

## Files

| File | What it does |
|---|---|
| `build_index.py` | Builds `web/index.json` from `eval/fixtures/docs/` (never from `docs/`), and `golden.json` for the check |
| `web/index.html` | Page structure and all styles |
| `web/scene.js` | The 3D hero (three.js): the word DEMO made of paper slips, posed six ways and blended by scroll position: the word, corpus, two searches, ranked list, the orders table, and a 3D chat panel like the page's own, onto which the slips land one line at a time (question, order query, document search, answer). The scene follows the scroll with a short lag; the panel is placed to fit the screen (beside the caption when wide, above it when narrow) |
| `web/search.js` | The query pipeline: embedding, BM25 keyword search, rank fusion, cross-encoder rerank, cutoff |
| `web/app.js` | Wires scroll to the scene, and the search box to `search.js`; renders results |
| `web/orders.js` | Order questions: query types, value extraction, per-role SQL views |
| `web/agent.js` | The agent chat (docked bottom-right): matches a typed question to a saved one, joins a reply to the question the agent asked back about, and draws each run as a chat reply (its steps, then the answer) |
| `web/liverun.js` | Runs an agent question with no saved run, live in the browser: SQL templates, then the policy search, no model |
| `web/roles.js` | Which role can open which documents; shared by the page and the check |
| `agent_runs.py` | Builds `web/agent.json`: each agent question run once per role through the real agent loop; `--check` verifies the committed file |
| `agent_examples.yaml` | The script for those runs: which steps to take and the answer's wording, per question and role |
| `web/agent.json` | The saved runs (committed): every step, what it returned, the answer |
| `check_search.mjs` | Runs the golden-set questions through `search.js`, `orders.js` and `agent.js` in Node; CI fails on any miss |

## The query path, step by step (`search.js`)

1. **Embed the question** with all-MiniLM-L6-v2 (Transformers.js, ONNX, int8).
2. **Meaning search**: dot product against every chunk's embedding (they are
   normalised, so this is cosine similarity); keep the top k.
3. **Keyword search**: BM25 with the same tokenizer and constants as the
   Python SQLite FTS5 index (`search/keyword.py`); keep the top k.
4. **Fuse** the two rankings with reciprocal rank fusion, the same formula as
   LangChain's `EnsembleRetriever` used in `rag.py`.
5. **Rerank**: ms-marco-MiniLM-L-6-v2 reads each candidate beside the
   question and scores it.
6. **Cutoff**: passages scoring below -6 are dropped. If none remain, the page
   says the documents don't cover the question. (Calibrated on this corpus:
   answering passages score about -4 to +8, unrelated ones about -11.)

## Run it locally

```bash
python demo/build_index.py
python -m http.server 8765 --directory demo/web   # then open http://localhost:8765
```

Check the browser search against the golden set:

```bash
python demo/agent_runs.py --check     # the saved agent runs are current
npm install --prefix demo/.node @huggingface/transformers@3.7.1 sql.js@1.15.2
node demo/check_search.mjs
```

## The interactive parts (`app.js`)

| Part | What it proves | How it works |
|---|---|---|
| **Where company search breaks** | Four real failure modes, run live | Each card runs a preset question. The "What just happened" text is computed from that run's actual rankings, never written in advance |
| **Search as** (Admin / Engineer / HR / Contractor) | Permissions are enforced, not just hidden | Each role maps to the files it may open; `search.js` drops everything else *before* retrieval, as the Python app's group filter does. A blocked file gets the same "not covered" message as a missing one, so its existence doesn't leak |
| **Pipeline X-ray** | Why hybrid search beats either half alone | The four ranked lists side by side; hover a passage to follow it across them |
| **Requests since the models loaded** | Nothing you type leaves the browser | A `PerformanceObserver` counts every network request after load. Anyone can confirm it in DevTools |

## Ask the orders (`orders.js`)

Order questions run against a real SQLite database in the browser (sql.js,
built in CI from `eval/fixtures/orders.sql`). There's no language model, so
`orders.js` is a **pattern translator**: it matches the question to one of
nine query types by meaning (the same embedding model the document search
loads), pulls out the order number, customer, status and dates, and fills in
a **parameterized** SQL template. Nothing typed ever becomes SQL text.

- It leads with the answer as a sentence, written from the result rows by a
  per-query-type summarizer (so it can't say anything the query didn't return,
  and it says "prices are hidden" rather than leaking a total). The rows, the
  policy passage, and the SQL with its parameters sit below as evidence.
- Below a similarity of 0.45 it says it can't turn the question into a query
  instead of guessing (paraphrased order questions scored 0.51+, document and
  off-topic questions at most 0.36).
- Roles apply through views rebuilt per query: Engineer sees prices as
  hidden, Contractor sees West-region orders only, HR has no access.
- For a held or late order, the matching policy passage from the documents is
  shown beside the row.
- "My orders" with no order number or customer asks which customer, instead
  of matching the nearest list ("where are my orders?" used to read as "which
  orders are on hold?"). Orders belong to customers, and the person signed in
  is staff. The full app's SQL prompt and agent carry the same rule.

`check_search.mjs` runs the golden set's 18 order cases through this code on
every deploy. The Python app answers open-ended order questions with Claude
(`search/orders.py`); `run_eval.py --live` checks it against the same cases.

## Ask the agent (`agent.js`)

The agent is a chat panel docked at the bottom right ("Ask the agent", or
"Agent" in the top bar), open from any section. Each reply lists the steps
taken, with the SQL, rows and passages folded under each step, then the answer
and a label saying which kind of run it was. The panel has its own role switch, separate from the page's "Search as":
changing it mid-conversation adds a note and applies to the next message,
and neither switch moves the other. The conversation lives in the page only.

The full app's agent (`agent.py`) calls Claude to choose its steps. This page
calls nothing, so it does two things instead: a question with a saved run
replays it, and any other question runs live, here, with fixed steps.

**Back and forth.** When the agent asks back ("Which customer's orders?"), a
short reply that is not itself a question ("Cobalt Bay Distribution", at most
8 words) is joined to the question it was asked about and run again; anything
else starts a new question. That is the only context carried between
messages: with no model, "and what about 1043?" is read as a new question on
its own. The full app's agent carries the whole conversation.
`check_search.mjs` holds the rule (asks back, reply answers, new question
doesn't inherit).

**Live runs** (`liverun.js`, labelled "Live run"). The same two halves as the
sections above, joined: the question goes through the SQL translator under
the role's views; for held or late orders, the policy that explains them is
found by document search under the role's document access (why late, then
one search per hold reason, at most 3); anything that isn't an order
question is a document search. The answer is the translator's sentence plus
the top passage of each search, so it says nothing the steps didn't return.
For a document question, the answer is the pieces of the top passage
(sentences, lines, or fields of an `a | b | c` line; at most 3) that share
the most words with the question, so "What is Sam Rivera's LinkedIn?" gets
the LinkedIn field rather than the resume's opening lines.
A role with no order access gets the full app's "no information" reply.

**Saved runs:**


- **What is real.** `agent_runs.py` runs each question once per role through
  the real agent loop: the SQL goes through the real guard and the role's
  views, the searches through real retrieval and the role's document access,
  and the agent's own checks apply (an answer with no evidence is replaced, a
  citation no step returned is dropped).
- **What is scripted.** The model is replaced by `agent_examples.yaml`: which
  steps to take and how the answer is worded. The page labels each run
  "Example run" and says so. `agent_runs.py --live` records the real agent
  instead (it calls Claude and costs money); the page then shows the model,
  timings and cost. That path has not been run yet.
- **Nothing unchecked ships.** The build fails if a scripted answer claims
  more than that role's steps returned, if a run holds something its role may
  not see (a file it cannot open, a customer email, a customer outside the
  Contractor's region), or if the Admin run misses the golden set's
  expectations for the question.
- **Staleness.** `agent.json` stores a fingerprint of the fixtures, prompts,
  tool definitions, model, questions, roles and example script.
  `agent_runs.py --check` recomputes it on every deploy, with no API call.
- **Typed questions.** A typed question is matched to a saved one by embedding
  similarity, and the page shows which saved question it matched. Measured on
  the golden set: rewordings scored 0.60 to 0.93 and look-alike questions up
  to 0.77, so no threshold separates them. The page uses 0.8 and requires the
  numbers in both questions to match (order 1043 never replays order 1042's
  answer), and one order never matches many ("where are my orders?" scored
  0.85 against the saved "where is my order?" but needs a different reply).
  8 of 14 test rewordings match a saved run; the rest run live.
- **Roles.** The role switch replays the run made for that role. On a static
  page that is an illustration, not security: every run ships with the page.

`check_search.mjs` checks, in the browser's own code, that the page's document
rules match the ones the runs were made under, that every question has a run
for every role, that no rewording replays a different question, that no
look-alike replays anything, and that the golden set's `demo_live` cases run
live and meet the same expectations the Python `--live` eval holds the real
agent to, and the chat's follow-up rule (64 checks in all).

## What it cannot do

There is no language model, so it quotes passages rather than writing
answers. It cannot count ("how many engineers?"), follow a pronoun in a
follow-up, or notice that a passage about someone doesn't contain the fact
asked for (a salary question returns their resume). The full Python app with
Claude does all three; `eval/run_eval.py --live` tests them. The agent section's live
runs take fixed steps, so they can't plan a question the templates don't cover.
