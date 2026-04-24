"""Track C: Frontier-CS 172-task algorithmic benchmark driver.

Runs GEPA and/or HELIX against Frontier-CS algorithmic problems with full
control over which models are used. Designed to run overnight on the M3
with either a local Ollama endpoint or the Colab tunnel for inference.

Model priority (largest/best free models first, in order)
---------------------------------------------------------
The default model priority for GEPA follows the current OpenRouter free
leaderboard as of April 2026:

  1. qwen/qwen3-coder:free         — 480B-A35B, best free coding MoE
  2. nvidia/nemotron-3-super-120b-a12b:free — 120B, strong SWE-bench
  3. minimax/minimax-m2.5:free     — 80.2% SWE-bench
  4. google/gemma-4-31b-it:free    — 31B dense, Apache 2.0
  5. qwen/qwen3-next-80b-a3b-instruct:free — 80B-A3B, fast

The task LM (generates solutions) and reflection LM (proposes mutations)
can be set independently. A good split:
  task_lm = qwen3-coder (best at writing code)
  reflection_lm = nemotron-3-super (best at reasoning about what to change)

Usage
-----
    # Smoke test — 5 problems, 5 calls each, best free model
    python track_c/run_frontier_cs.py --optimizer gepa --n-problems 5 --max-metric-calls 5

    # Explicit model
    python track_c/run_frontier_cs.py \\
        --optimizer gepa \\
        --task-model "openrouter/qwen/qwen3-coder:free" \\
        --reflection-model "openrouter/nvidia/nemotron-3-super-120b-a12b:free" \\
        --n-problems 172 --max-metric-calls 30

    # Full HELIX run (uses real Claude Code via Anthropic API)
    python track_c/run_frontier_cs.py --optimizer helix --n-problems 172

    # Model sweep — run the same 10 problems with 3 different models
    python track_c/run_frontier_cs.py \\
        --optimizer gepa --n-problems 10 --max-metric-calls 10 \\
        --sweep-models \\
        "openrouter/qwen/qwen3-coder:free,qwen/qwen3-coder:free" \\
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free,nvidia/nemotron-3-super-120b-a12b:free" \\
        "openrouter/google/gemma-4-31b-it:free,google/gemma-4-31b-it:free"

    # Compare after runs complete
    python -m core.results_aggregator \\
        --run results/gepa-algorithmic-qwen3-coder-free-<ts> \\
        --compare results/gepa-algorithmic-nemotron-3-super-<ts> \\
        --label "Qwen3-Coder 480B" --label-compare "Nemotron 3 Super" --latex
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time

from dotenv import load_dotenv

# Always load from project root .env regardless of cwd or shell exports
_ENV_PATH = pathlib.Path(__file__).parent.parent / '.env'
load_dotenv(_ENV_PATH, override=True)

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent))

from core.batch_runner import BatchRunner, RunConfig
from core.results_aggregator import ResultsAggregator, compare_runs


# --------------------------------------------------------------------------- #
# Model definitions
# --------------------------------------------------------------------------- #

# OpenRouter model IDs in priority order (largest/best free models first).
# Format: (openrouter_model_id, short_label)
FREE_MODEL_PRIORITY = [
    ("openrouter/qwen/qwen3-coder:free",                        "Qwen3-Coder-480B"),
    ("openrouter/nvidia/nemotron-3-super-120b-a12b:free",        "Nemotron3-Super-120B"),
    ("openrouter/minimax/minimax-m2.5:free",                    "MiniMax-M2.5"),
    ("openrouter/google/gemma-4-31b-it:free",                   "Gemma4-31B"),
    ("openrouter/qwen/qwen3-next-80b-a3b-instruct:free",         "Qwen3-Next-80B"),
]

# Best reflection model (reasoning-heavy, doesn't need to write C++)
DEFAULT_REFLECTION_MODEL = "openrouter/minimax/minimax-m2.5:free"


def _best_free_task_model() -> str:
    """Return the highest-priority free model from FREE_MODEL_PRIORITY."""
    return FREE_MODEL_PRIORITY[0][0]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _get_problem_ids(frontier_repo: str, n: int) -> list[int]:
    problems_dir = pathlib.Path(frontier_repo) / "algorithmic" / "problems"
    if not problems_dir.exists():
        raise FileNotFoundError(
            f"Frontier-CS algorithmic/problems/ not found at {problems_dir}. "
            "Check FRONTIER_CS_REPO in .env."
        )
    available = sorted(
        int(d.name) for d in problems_dir.iterdir()
        if d.is_dir() and d.name.isdigit()
    )
    print(f"Found {len(available)} algorithmic problems in repo.")
    chosen = available[:n]
    suffix = "..." if len(chosen) < len(available) else ""
    print(f"Using {len(chosen)} problems: {chosen[:5]}{suffix}")
    return chosen


def _run_single(
    *,
    optimizer: str,
    problem_ids: list[int],
    task_model: str,
    reflection_model: str,
    args: argparse.Namespace,
) -> tuple[pathlib.Path, str]:
    """Run one (optimizer, model) combination. Returns (run_dir, label)."""
    label = args.label or f"{optimizer.upper()} {task_model.split('/')[-1]}"
    cfg = RunConfig(
        optimizer=optimizer,
        track="algorithmic",
        problem_ids=problem_ids,
        task_model=task_model,
        reflection_model=reflection_model,
        helix_claude_model=args.helix_claude_model,
        max_metric_calls=args.max_metric_calls,
        max_generations=args.max_generations,
        max_evaluations=args.max_evaluations,
        max_turns=args.max_turns,
        max_workers=args.max_workers,
        results_root=args.results_dir,
        resume=args.resume,
        timeout_per_problem=args.timeout,
        experiment_tag="track_c",
    )
    runner = BatchRunner(cfg)
    t0 = time.monotonic()
    runner.run()
    elapsed = time.monotonic() - t0
    print(f"\n{optimizer.upper()} run complete in {elapsed / 60:.1f} min")
    runner.print_summary()

    # Save paper metrics immediately
    agg = ResultsAggregator(runner.results_root)
    agg.print_summary(label=label)
    agg.save_json(label=label)
    print("LaTeX row:", agg.to_latex_row(label=label))

    return runner.results_root, label


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Track C: Frontier-CS 172-task algorithmic benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    ap.add_argument("--optimizer", required=True,
                    choices=["gepa", "helix", "both"],
                    help="Which optimizer to run.")
    ap.add_argument("--n-problems", type=int, default=5,
                    help="Number of problems (IDs 0..N-1). Default 5 = smoke test.")

    # ── Model selection ──────────────────────────────────────────────────────
    model_grp = ap.add_argument_group("Model selection")
    model_grp.add_argument(
        "--task-model", default="",
        help=(
            "LiteLLM model ID for the task LM (generates solutions). "
            "Default: highest-priority free model from FREE_MODEL_PRIORITY. "
            "Example: 'qwen/qwen3-coder:free'"
        ),
    )
    model_grp.add_argument(
        "--reflection-model", default="",
        help=(
            "LiteLLM model ID for the reflection LM (proposes mutations). "
            f"Default: {DEFAULT_REFLECTION_MODEL}. "
            "Can differ from --task-model to split load across providers."
        ),
    )
    model_grp.add_argument(
        "--helix-claude-model", default="sonnet",
        help="HELIX [claude] model field (default: 'sonnet'). "
             "Only relevant when --optimizer=helix.",
    )
    model_grp.add_argument(
        "--sweep-models", nargs="*", metavar="TASK,REFLECTION",
        help=(
            "Run the same problems with multiple model pairs. "
            "Provide space-separated 'task_model,reflection_model' strings. "
            "Results are saved separately and compared at the end."
        ),
    )
    model_grp.add_argument(
        "--use-default-priority", action="store_true",
        help="Sweep all models in FREE_MODEL_PRIORITY order (ignores --task-model).",
    )

    # ── Budgets ──────────────────────────────────────────────────────────────
    budget_grp = ap.add_argument_group("Budgets")
    budget_grp.add_argument("--max-metric-calls", type=int, default=30)
    budget_grp.add_argument("--max-generations", type=int, default=5)
    budget_grp.add_argument("--max-evaluations", type=int, default=20)
    budget_grp.add_argument("--max-turns", type=int, default=10)

    # ── Infrastructure ────────────────────────────────────────────────────────
    infra_grp = ap.add_argument_group("Infrastructure")
    infra_grp.add_argument("--max-workers", type=int, default=4)
    infra_grp.add_argument("--timeout", type=int, default=1800)
    infra_grp.add_argument("--results-dir", default="results")
    infra_grp.add_argument("--resume", action="store_true", default=True)
    infra_grp.add_argument("--no-resume", dest="resume", action="store_false")
    infra_grp.add_argument("--label", default="",
                           help="Human-readable label for the run (used in paper tables).")

    return ap.parse_args()


def main() -> int:
    args = _parse_args()

    frontier_repo = os.environ.get("FRONTIER_CS_REPO", "../Frontier-CS")
    problem_ids = _get_problem_ids(frontier_repo, args.n_problems)

    # ── Build list of (task_model, reflection_model) pairs to run ────────────
    pairs: list[tuple[str, str]] = []

    if args.use_default_priority:
        for task_m, _ in FREE_MODEL_PRIORITY:
            pairs.append((task_m, DEFAULT_REFLECTION_MODEL))

    elif args.sweep_models:
        for spec in args.sweep_models:
            parts = spec.split(",", 1)
            t = parts[0].strip()
            r = parts[1].strip() if len(parts) > 1 else DEFAULT_REFLECTION_MODEL
            pairs.append((t, r))

    else:
        t = args.task_model or os.environ.get("TASK_MODEL") or _best_free_task_model()
        r = args.reflection_model or os.environ.get("REFLECTION_MODEL") or DEFAULT_REFLECTION_MODEL
        pairs.append((t, r))

    # ── Execute ───────────────────────────────────────────────────────────────
    optimizers = (["gepa", "helix"] if args.optimizer == "both"
                  else [args.optimizer])

    all_runs: list[tuple[pathlib.Path, str]] = []  # (run_dir, label)

    for optimizer in optimizers:
        for task_m, refl_m in pairs:
            t_label = task_m.split("/")[-1].replace(":free","")
            r_label = refl_m.split("/")[-1].replace(":free","")
            print(f"\n{'#'*65}")
            print(f"# optimizer : {optimizer.upper()}")
            print(f"# task_lm   : {task_m}  ({t_label})")
            print(f"# refl_lm   : {refl_m}  ({r_label})")
            print(f"{'#'*65}")

            run_dir, label = _run_single(
                optimizer=optimizer,
                problem_ids=problem_ids,
                task_model=task_m,
                reflection_model=refl_m,
                args=args,
            )
            all_runs.append((run_dir, label))

    # ── Cross-run comparison ──────────────────────────────────────────────────
    if len(all_runs) >= 2:
        print(f"\n{'='*65}")
        print("Cross-run comparison (first vs. last)")
        print(f"{'='*65}")
        compare_runs(
            all_runs[0][0], all_runs[-1][0],
            label_a=all_runs[0][1], label_b=all_runs[-1][1],
            latex=True,
        )

    # Print all LaTeX rows together
    if len(all_runs) > 1:
        print("\n-- All LaTeX rows --")
        for run_dir, label in all_runs:
            agg = ResultsAggregator(run_dir)
            print(agg.to_latex_row(label=label))

    return 0


if __name__ == "__main__":
    sys.exit(main())
