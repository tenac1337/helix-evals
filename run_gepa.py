"""Run GEPA optimize_anything against a Frontier-CS algorithmic problem.

Talks to the open-weight model served from Colab via the Cloudflare tunnel
in OPENAI_BASE_URL. Talks to Frontier-CS via Docker (real backend, M3 only).

Usage:
    python run_gepa.py --track algorithmic --problem 0 --max-metric-calls 30
    python run_gepa.py --problem 0,1,2,3 --max-metric-calls 150  # multi-task
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

from dotenv import load_dotenv

load_dotenv()  # populates os.environ from ./.env

import gepa
from gepa import optimize_anything

from frontier_adapter import FrontierCSAdapter, FrontierTask
from seed_cpp import SEED_CPP


def _parse_problems(track: str, raw: str) -> list[FrontierTask]:
    out: list[FrontierTask] = []
    for p in [x.strip() for x in raw.split(",") if x.strip()]:
        if track == "algorithmic":
            pid: int | str = int(p) if p.isdigit() else p
            out.append(FrontierTask(track=track, problem_id=pid, language="cpp"))
        else:
            out.append(FrontierTask(track=track, problem_id=p, language="python"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="algorithmic", choices=["algorithmic", "research"])
    ap.add_argument("--problem", required=True,
                    help="Problem id, or comma-separated ids for multi-task search")
    ap.add_argument("--max-metric-calls", type=int, default=30)
    ap.add_argument("--objective", default=(
        "Maximize Frontier-CS score on the target problem(s). The candidate is "
        "C++ source for the algorithmic track. Use compiler diagnostics, runtime "
        "output, and per-test-case scores in the ASI to diagnose failures and "
        "iteratively improve the solution."
    ))
    args = ap.parse_args()

    # Sanity-check that the tunnel env vars are in place.
    for var in ("OPENAI_BASE_URL", "OPENAI_API_KEY"):
        if not os.environ.get(var):
            sys.exit(f"Missing env var: {var}. Did you fill in .env?")
    if "trycloudflare" not in os.environ["OPENAI_BASE_URL"] and \
            "localhost" not in os.environ["OPENAI_BASE_URL"]:
        print(f"WARNING: OPENAI_BASE_URL doesn't look like a tunnel URL: "
              f"{os.environ['OPENAI_BASE_URL']}", file=sys.stderr)

    tasks = _parse_problems(args.track, args.problem)
    print(f"Running GEPA on {len(tasks)} task(s): {[t.key for t in tasks]}")
    print(f"Task LM:        {os.environ.get('TASK_MODEL', '<unset>')}")
    print(f"Reflection LM:  {os.environ.get('REFLECTION_MODEL', '<unset>')}")
    print(f"OpenAI base:    {os.environ['OPENAI_BASE_URL']}")

    adapter = FrontierCSAdapter(backend="docker", unbounded=True)
    evaluator = adapter.make_optimize_anything_evaluator(tasks)

    results_root = pathlib.Path(os.environ.get("RESULTS_DIR", "./results"))
    log_dir = results_root / f"gepa-{args.track}-{int(time.time())}"
    log_dir.mkdir(parents=True, exist_ok=True)

    common = dict(
        seed_candidate=SEED_CPP,
        evaluator=evaluator,
        objective=args.objective,
        task_lm=os.environ.get("TASK_MODEL", "openai/task-model"),
        reflection_lm=os.environ.get("REFLECTION_MODEL", "openai/task-model"),
        max_metric_calls=args.max_metric_calls,
        log_dir=str(log_dir),
    )
    if len(tasks) == 1:
        result = optimize_anything(**common)
    else:
        result = optimize_anything(dataset=tasks, **common)

    best_path = log_dir / "best_candidate.cpp"
    best_path.write_text(
        result.best_candidate if isinstance(result.best_candidate, str)
        else json.dumps(result.best_candidate, indent=2)
    )
    summary = {
        "track": args.track,
        "problems": [t.key for t in tasks],
        "task_lm": common["task_lm"],
        "reflection_lm": common["reflection_lm"],
        "max_metric_calls": args.max_metric_calls,
        "best_score": getattr(result, "best_score", None),
        "best_candidate_path": str(best_path),
        "tunnel": os.environ["OPENAI_BASE_URL"],
    }
    (log_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 60)
    print(f"Best score:     {summary['best_score']}")
    print(f"Best candidate: {best_path}")
    print(f"Log dir:        {log_dir}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
