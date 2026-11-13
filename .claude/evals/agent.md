# EVAL DEFINITION: agent

Evals for the agent (`agent.py`) and the demo page's agent section.

## Capability evals (model-graded and code-graded, `--live` tier)

Cases: `mode: agent` in `eval/fixtures/golden_set.yaml`. Run with
`python eval/run_eval.py --live --golden-set eval/fixtures/golden_set.yaml`
(calls Claude; costs money). Graders: code (`check_agent_result`: tools that
returned a result, row values, hidden columns, cited files, answer keywords)
plus the groundedness judge over what the agent read.

1. agent-held-order-action: order row + hold policy + support action
2. agent-late-holds-explained: several rows, one search per hold reason
3. agent-warranty-check: delivery date + warranty period
4. agent-catalog-then-count: a document fact feeds the query
5. agent-late-by-region: aggregate + playbook
6. agent-needs-order-number: asks a clarifying question
7. agent-not-in-documents: refuses
8. agent-contractor-west-only: role scope holds across steps
9. agent-engineer-emails-hidden: hidden column stays hidden
10. agent-hr-no-orders: no order access
11. agent-my-orders: asks which customer
12. agent-other-order-late: unsaved order, query + playbook
13. agent-customer-orders: a named customer's orders
14. agent-off-topic: refuses

Target: pass@3 >= 90%. Status: defined, not yet run.

## Regression evals (code-graded, free, every change)

- `python -m pytest tests/ -q` (includes `tests/test_agent.py`: permissions,
  SQL guard, bounds, grounding, logging, with a scripted model)
- `python eval/run_eval.py --golden-set eval/fixtures/golden_set.yaml`
- `python demo/agent_runs.py --check`
- `python demo/build_index.py && node demo/check_search.mjs`

Target: pass^3 = 100%.

## Last run (2026-11-12)

- pytest: 288 passed
- agent_runs --check: current (7 questions x 4 roles, example runs)
- check_search.mjs: 60 passed, 0 failed (8 of 14 rewordings matched a saved
  run; 5 demo_live cases ran live and met their expectations)
- retrieval eval: 15 passed, 0 failed, 40 skipped (orders and agent cases need --live)
