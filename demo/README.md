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
| `web/scene.js` | The 3D hero (three.js): the word DEMO made of paper slips, posed four ways and blended by scroll position |
| `web/search.js` | The query pipeline: embedding, BM25 keyword search, rank fusion, cross-encoder rerank, cutoff |
| `web/app.js` | Wires scroll to the scene, and the search box to `search.js`; renders results |
| `check_search.mjs` | Runs the golden-set questions through `search.js` in Node; CI fails on any miss |

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
npm install --prefix demo/.node @huggingface/transformers@3.7.1
node demo/check_search.mjs
```

## The interactive parts (`app.js`)

| Part | What it proves | How it works |
|---|---|---|
| **Where company search breaks** | Four real failure modes, run live | Each card runs a preset question. The "What just happened" text is computed from that run's actual rankings, never written in advance |
| **Search as** (Admin / Engineer / HR / Contractor) | Permissions are enforced, not just hidden | Each role maps to the files it may open; `search.js` drops everything else *before* retrieval, as the Python app's group filter does. A blocked file gets the same "not covered" message as a missing one, so its existence doesn't leak |
| **Pipeline X-ray** | Why hybrid search beats either half alone | The four ranked lists side by side; hover a passage to follow it across them |
| **Requests since the models loaded** | Nothing you type leaves the browser | A `PerformanceObserver` counts every network request after load. Anyone can confirm it in DevTools |

## What it cannot do

There is no language model, so it quotes passages rather than writing
answers. It cannot count ("how many engineers?"), follow a pronoun in a
follow-up, or notice that a passage about someone doesn't contain the fact
asked for (a salary question returns their resume). The full Python app with
Claude does all three; `eval/run_eval.py --live` tests them.
