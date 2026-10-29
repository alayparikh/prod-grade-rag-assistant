# Fixtures: Acme Robotics

A fictional company used by CI, the evals and the public demo. Nothing here
is real: names, emails (`@example.com`), phone numbers (`555-01xx`), URLs
(`*.example.com`) and companies are all invented. Your own documents go in
`docs/`, which is git-ignored and never read by any of this.

## What's here

| Path | What it is |
|---|---|
| `docs/` | 18 documents: the business side (product catalog, order lifecycle, shipping policy, returns & warranty, support playbook), the engineering side (handbook, architecture notes, runbooks, security and testing policy, onboarding) and people (team roster, six resumes, one of them a `.docx` with hyperlinks) |
| `orders.sql` | The orders database: 12 customers, 3 products, 80 orders with items and tracking events. **Generated, don't edit by hand** |
| `make_orders.py` | Writes `orders.sql`. Deterministic, with a fixed "today" of 2026-10-28 stored in the `meta` table, so answers never drift |
| `golden_set.yaml` | The eval questions and their expected answers, for documents, file search and orders |

## Story orders

Most orders are generated filler; ten are written by hand so questions have
interesting answers. Each one's explanation is in the docs:

| Order | State | Explained by |
|---|---|---|
| 1042 | on hold, `address_verification`, late | `shipping_policy.md` |
| 1043 | shipped, late | `support_playbook.md` |
| 1044 | on hold, `export_license` (EU PR-900) | `shipping_policy.md` |
| 1045 | on hold, `credit_check` | `shipping_policy.md` |
| 1047 | returned | `returns_warranty.md` |
| 1048 | on hold, `site_readiness` | `shipping_policy.md` |
| 1049 | on hold, `payment_failed` | `shipping_policy.md` |
| 1051 | delivered three days late | `support_playbook.md` |

Lead and transit times in the data come from the same numbers the catalog
and shipping policy state, so a promised date can always be explained.

## Changing the fixtures

The golden set's expectations are grounded in these files. After editing a
document or regenerating `orders.sql`, update the matching cases and run:

```bash
python eval/fixtures/make_orders.py                          # if the data changed
python eval/run_eval.py --golden-set eval/fixtures/golden_set.yaml
python demo/build_index.py && node demo/check_search.mjs     # the browser demo's checks
```
