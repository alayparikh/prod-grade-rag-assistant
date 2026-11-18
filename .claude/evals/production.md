# EVAL DEFINITION: production

Evals that prove the system holds at production scale and under failure,
not only that it answers the golden set. The failure scenarios each one
covers are in `PRODUCTION_READINESS.md`.

## Regression evals (code-graded, free, every push in CI)

| Suite | Command (CI size) | Proves |
|---|---|---|
| Unit + fault injection | `python -m pytest tests/ -q` | Bounds, fail-closed paths, 429/timeout handling, corrupt orders DB, killed index run resumes, rate limit under concurrency, readiness |
| Adversarial SQL | `pytest tests/test_sql_attacks.py` (corpus `eval/adversarial/sql_attacks.yaml`) | Every write/escape/function attack rejected; resource bombs bounded; role views hold |
| Retrieval vs baseline | `python eval/run_eval.py --golden-set eval/fixtures/golden_set.yaml --baseline eval/baseline_retrieval.json` | No case regresses from PASS; MRR within 0.05 |
| Scale bench | `python eval/scale/bench.py all --files 300 --sizes 200,2000` | No-op re-run re-embeds nothing and keeps the cache; 1% change re-embeds 1%; killed run resumes; query heap flat as corpus grows 10x |
| SQL load | `python eval/load/sql_load.py --orders 20000 --workers 8 --queries 400` | No crash under concurrency; attacks bounded; contractor isolation holds |
| Agent load | `python eval/load/agent_load.py --questions 200 --workers 16` | Step/call/time caps hold under 429s, timeouts, slow and runaway models; no cross-user leakage |

Target: pass^3 = 100% (all deterministic or seeded).

## Capability evals (`--live`, manual, cost money)

| Suite | Command | Target |
|---|---|---|
| Golden set, repeated | `python eval/run_eval.py --live --golden-set eval/fixtures/golden_set.yaml --metrics --repeat 3` | pass@3 >= 0.90 overall; pass^3 = 1.00 for `safety` and role cases |
| Prompt injection | `build_corpus.py` then `run_eval.py --live --golden-set eval/adversarial/injection.yaml` | pass^3 = 1.00 |

Status: defined, **not yet run** (needs an API key and spend approval).

## Larger runs (manual, before a capacity decision)

- `python eval/scale/bench.py all --files 5000 --sizes 1000,20000`
- `python eval/scale/bench.py index --files 500 --real-embeddings` (embedding throughput)
- `python eval/load/sql_load.py --orders 200000 --workers 16 --queries 2000 [--indexes]`

Measured results are recorded in `PRODUCTION_READINESS.md` with the date
and machine; rerun them on the target hardware before sizing it.
