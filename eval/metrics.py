"""Eval metrics: ranking quality, latency, cost, repeat reliability, baselines.

PASS/FAIL per case answers "did it work". These answer the questions a
production change actually raises:

- Did retrieval get worse even though every case still passes?
  hit@k and MRR over the rank of the first chunk holding an expected fact.
- Did it get slower?  p50 / p95 per-case latency.
- Did it get more expensive?  tokens and cost per question, from the event
  log the app already writes (mode=eval), so the numbers are the same ones
  production dashboards would show.
- Is it reliable or did it pass by luck?  pass@k (any of k runs passed) and
  pass^k (all k passed) over repeated live runs.

A results file can be saved as a baseline; a later run compared to it fails
on a case that regressed from PASS, an MRR drop, or a p95 blow-up.
"""
import json
import math
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "eval", "results")

# Regression thresholds against a baseline. Latency gets an absolute floor on
# top of the ratio: a 40 ms p95 doubling to 80 ms on a noisy CI runner is not
# a regression worth failing a build for.
MAX_MRR_DROP = 0.05
MAX_P95_RATIO = 2.0
P95_NOISE_FLOOR_MS = 250
HIT_KS = (1, 3, 5)


def percentile(values, p):
    """Nearest-rank percentile; None for no values."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    rank = max(1, math.ceil(p / 100 * len(values)))
    return values[rank - 1]


def expected_keywords(item):
    return item.get("expect_answer_contains_any") or item.get("expect_answer_contains_all") or []


def first_hit_rank(item, docs):
    """1-based rank of the first chunk holding any expected keyword, or None.

    A proxy for "rank of the first relevant chunk" that needs no labelled
    chunk ids: the golden set already says which facts an answer needs."""
    keywords = [k.lower() for k in expected_keywords(item)]
    if not keywords:
        return None
    for i, doc in enumerate(docs, start=1):
        text = doc.page_content.lower()
        if any(k in text for k in keywords):
            return i
    return None


def summarize(results, case_metrics):
    """results: [(id, status, reason)]; case_metrics: {id: {"ms", "rank", ...}}."""
    statuses = [r[1] for r in results]
    ranked = [m for m in case_metrics.values() if m.get("ranked")]
    ranks = [m.get("rank") for m in ranked]
    latencies = [m.get("ms") for m in case_metrics.values()]
    summary = {
        "total": len(results),
        "passed": statuses.count("PASS"),
        "failed": statuses.count("FAIL"),
        "errored": statuses.count("ERROR"),
        "skipped": statuses.count("SKIP"),
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
    }
    if ranked:
        summary["ranked_cases"] = len(ranked)
        summary["mrr"] = round(sum(1 / r for r in ranks if r) / len(ranked), 4)
        for k in HIT_KS:
            summary[f"hit@{k}"] = round(sum(1 for r in ranks if r and r <= k) / len(ranked), 4)
    return summary


def repeat_reliability(runs):
    """runs: list of result lists from k repeated runs. Per case pass@k / pass^k.

    ERROR (API failure) counts as not passing: an eval that can't reach the
    model has not shown the behaviour."""
    by_case = {}
    for results in runs:
        for id_, status, _ in results:
            by_case.setdefault(id_, []).append(status)
    scored = {id_: s for id_, s in by_case.items() if any(x != "SKIP" for x in s)}
    k = len(runs)
    if not scored:
        return {"k": k}
    any_pass = sum(1 for s in scored.values() if "PASS" in s)
    all_pass = sum(1 for s in scored.values() if all(x == "PASS" for x in s))
    return {
        "k": k,
        "cases": len(scored),
        f"pass@{k}": round(any_pass / len(scored), 4),
        f"pass^{k}": round(all_pass / len(scored), 4),
        "flaky": sorted(id_ for id_, s in scored.items() if "PASS" in s and not all(x == "PASS" for x in s)),
    }


def usage_from_log(log_path, since_ts):
    """Tokens, cost and latency of every eval-mode question logged since
    since_ts. Streams the log; never holds it in memory."""
    totals = {"questions": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
              "unpriced_questions": 0}
    latencies = []
    if not os.path.exists(log_path):
        return totals
    with open(log_path) as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("ts", 0) < since_ts or event.get("mode") != "eval":
                continue
            totals["questions"] += 1
            totals["input_tokens"] += event.get("input_tokens") or 0
            totals["output_tokens"] += event.get("output_tokens") or 0
            if event.get("cost_usd") is None:
                totals["unpriced_questions"] += 1
            else:
                totals["cost_usd"] += event["cost_usd"]
            latencies.append(event.get("latency_ms"))
    totals["cost_usd"] = round(totals["cost_usd"], 4)
    if totals["questions"]:
        totals["cost_per_question_usd"] = round(totals["cost_usd"] / totals["questions"], 5)
        totals["latency_p50_ms"] = percentile(latencies, 50)
        totals["latency_p95_ms"] = percentile(latencies, 95)
    return totals


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_report(mode, golden_set, results, case_metrics, extra=None):
    return {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_sha": git_sha(),
        "mode": mode,
        "golden_set": os.path.relpath(golden_set, ROOT),
        "summary": summarize(results, case_metrics),
        **(extra or {}),
        "cases": [{"id": id_, "status": status, "reason": reason, **case_metrics.get(id_, {})}
                  for id_, status, reason in results],
    }


def write_report(report, path=None):
    path = path or os.path.join(RESULTS_DIR, f"{report['mode']}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def baseline_view(report):
    """The report without anything machine- or run-specific (latency, time,
    commit), so a committed baseline does not fail CI because the runner is
    slower than the laptop it was recorded on."""
    summary = {k: v for k, v in report["summary"].items() if not k.startswith("latency")}
    cases = [{k: v for k, v in c.items() if k != "ms"} for c in report["cases"]]
    return {"mode": report["mode"], "golden_set": report["golden_set"], "summary": summary, "cases": cases}


def compare(report, baseline):
    """Problems that make this run a regression against the baseline."""
    problems = []
    before = {c["id"]: c["status"] for c in baseline.get("cases", [])}
    for case in report["cases"]:
        if before.get(case["id"]) == "PASS" and case["status"] in ("FAIL", "ERROR"):
            problems.append(f"{case['id']}: PASS -> {case['status']} ({case.get('reason', '')})")

    now, then = report["summary"], baseline.get("summary", {})
    if now.get("mrr") is not None and then.get("mrr") is not None \
            and then["mrr"] - now["mrr"] > MAX_MRR_DROP:
        problems.append(f"MRR dropped {then['mrr']} -> {now['mrr']} (allowed {MAX_MRR_DROP})")
    p95_now, p95_then = now.get("latency_p95_ms"), then.get("latency_p95_ms")
    if p95_now is not None and p95_then is not None \
            and p95_now > max(p95_then * MAX_P95_RATIO, p95_then + P95_NOISE_FLOOR_MS):
        problems.append(f"p95 latency {p95_then} -> {p95_now} ms (allowed x{MAX_P95_RATIO})")
    return problems
