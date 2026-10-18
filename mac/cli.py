"""mac: run a strategy over HumanEval, rescore recorded solutions, and compare strategies."""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

from . import agents, bench, llm

log = logging.getLogger("mac")
STRATEGIES = ("single", "exec-feedback", "full")


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def cmd_run(args) -> None:
    out = Path(f"runs/{args.strategy}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["task_id"] for r in _load(out)}
    tasks = {t.task_id: t for t in bench.load()}
    digest = llm.model_digest(args.model)
    with out.open("a") as f:
        for i, task in enumerate(list(tasks.values())[: args.limit], 1):
            if task.task_id in done:
                continue
            outcome = agents.solve(task, args.strategy, args.model, args.max_revisions)
            record = {**outcome.__dict__, "model": args.model, "model_digest": digest,
                      "hidden": agents.score(task, outcome.final_code)}
            f.write(json.dumps(record) + "\n")
            f.flush()
            log.info("%s %s: hidden=%s approved=%s calls=%d", args.strategy, task.task_id,
                     record["hidden"]["passed"], outcome.approved, outcome.usage["calls"])


def cmd_rescore(args) -> None:
    """Re-execute the recorded final code against the hidden tests (no model needed)."""
    tasks = {t.task_id: t for t in bench.load()}
    mismatches = 0
    for path in sorted(Path(args.runs_dir).glob("*.jsonl")):
        for r in _load(path):
            now = agents.score(tasks[r["task_id"]], r["final_code"])["passed"]
            if now != r["hidden"]["passed"]:
                mismatches += 1
                print(f"MISMATCH {path.name} {r['task_id']}: recorded {r['hidden']['passed']} now {now}")
    print(f"rescore complete, {mismatches} mismatches")
    sys.exit(1 if mismatches else 0)


def _bootstrap_diff(a: list[int], b: list[int], seed: int = 0, n: int = 10_000) -> list[float]:
    rng = random.Random(seed)
    d = [y - x for x, y in zip(a, b)]
    stats = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(n))
    return [round(stats[int(0.025 * n)], 4), round(stats[int(0.975 * n) - 1], 4)]


def cmd_compare(args) -> None:
    runs = {s: {r["task_id"]: r for r in _load(Path(args.runs_dir) / f"{s}.jsonl")} for s in STRATEGIES}
    common = sorted(set.intersection(*(set(v) for v in runs.values() if v)) if any(runs.values()) else set())
    if not common:
        raise ValueError("No paired tasks across the selected saved runs")
    summary = {"tasks": len(common), "strategies": {}}
    for s, recs in runs.items():
        if not recs:
            continue
        rs = [recs[t] for t in common]
        passed = [int(r["hidden"]["passed"]) for r in rs]
        approved = [r for r in rs if r["approved"]]
        summary["strategies"][s] = {
            "pass_at_1": round(sum(passed) / len(rs), 4),
            "mean_llm_calls": round(sum(r["usage"]["calls"] for r in rs) / len(rs), 2),
            "mean_output_tokens": round(sum(r["usage"]["output_tokens"] for r in rs) / len(rs), 1),
            "mean_seconds": round(sum(r["usage"]["seconds"] for r in rs) / len(rs), 2),
            "approved": len(approved) if s != "single" else None,
            "approved_but_hidden_failed": sum(not r["hidden"]["passed"] for r in approved) if s != "single" else None,
            "revised_tasks": sum(len(r["attempts"]) > 1 for r in rs),
        }
    base = runs.get("single")
    if base:
        b = [int(base[t]["hidden"]["passed"]) for t in common]
        for s in ("exec-feedback", "full"):
            if runs.get(s):
                c = [int(runs[s][t]["hidden"]["passed"]) for t in common]
                summary["strategies"][s]["vs_single"] = {
                    "pass_diff": round((sum(c) - sum(b)) / len(common), 4),
                    "ci95": _bootstrap_diff(b, c),
                    "fixed": sum(1 for x, y in zip(b, c) if y > x),
                    "broken": sum(1 for x, y in zip(b, c) if x > y),
                }
    text = json.dumps(summary, indent=2)
    Path(args.report).write_text(text + "\n")
    print(text)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="mac")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run")
    s.add_argument("strategy", choices=STRATEGIES)
    s.add_argument("--model", default="qwen2.5:3b")
    s.add_argument("--limit", type=int)
    s.add_argument("--max-revisions", type=int, default=2)
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("rescore")
    s.add_argument("--runs-dir", default="runs")
    s.set_defaults(fn=cmd_rescore)
    s = sub.add_parser("compare")
    s.add_argument("--runs-dir", default="runs")
    s.add_argument("--report", default="docs/comparison.json")
    s.set_defaults(fn=cmd_compare)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
