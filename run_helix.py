"""Run HELIX (whole-repo agentic mutation) against a Frontier-CS algorithmic problem.

HELIX needs a git-initialized project directory containing:
    helix.toml
    evaluate.py   (emits json {"score": ...} to stdout)
    solve.cpp     (the candidate HELIX evolves)

This script generates that structure, sets ANTHROPIC_BASE_URL so HELIX's
`claude` subprocesses speak to the Colab tunnel instead of Anthropic, and
runs `helix evolve`.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import textwrap
import time

from dotenv import load_dotenv

load_dotenv()


HELIX_TOML_TEMPLATE = """\
objective = "Maximize Frontier-CS score for the target problem. Edit solve.cpp so that running evaluate.py yields the highest possible score from frontier_cs.SingleEvaluator."

seed = "."
rng_seed = 0

[evaluator]
command = "python evaluate.py"
score_parser = "json_score"
include_stdout = true
include_stderr = true
protected_files = ["evaluate.py", "problem.json"]

[evolution]
max_generations = {max_gens}
max_evaluations = {max_evals}
merge_enabled = false
minibatch_size = 1
cache_evaluation = true
acceptance_criterion = "strict_improvement"

[claude]
model = "sonnet"
effort = "medium"
max_turns = {max_turns}
allowed_tools = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]
background = "Only modify solve.cpp. Do not edit evaluate.py or problem.json — they are the benchmark harness."

[worktree]
base_dir = ".helix/worktrees"
"""

EVALUATE_PY_TEMPLATE = '''\
"""HELIX evaluator — calls Frontier-CS via Docker on the M3."""
import json, os, pathlib, sys, traceback
sys.path.insert(0, "{adapter_dir}")
from frontier_adapter import FrontierCSAdapter, FrontierTask  # noqa

root = pathlib.Path(__file__).parent
spec = json.loads((root / "problem.json").read_text())
code = (root / "solve.cpp").read_text()

try:
    adapter = FrontierCSAdapter(backend="docker", unbounded=True)
    score, asi = adapter.evaluate(code, FrontierTask(
        track=spec["track"], problem_id=spec["problem_id"], language="cpp",
    ))
    print(json.dumps({{
        "score": score,
        "instance_scores": {{str(spec["problem_id"]): score}},
        "asi": asi[:8000],   # cap so HELIX's reflection prompt isn't gigantic
    }}))
except Exception as exc:
    print(json.dumps({{
        "score": 0.0,
        "instance_scores": {{str(spec["problem_id"]): 0.0}},
        "error": f"{{type(exc).__name__}}: {{exc}}",
        "traceback": traceback.format_exc(),
    }}))
'''

SEED_SOLVE_CPP = """\
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    string line;
    while (getline(cin, line)) { /* discard */ }

    cout << 0 << endl;
    return 0;
}
"""


def setup_helix_project(work_dir: pathlib.Path, *, track: str, problem_id,
                        adapter_dir: str, max_gens: int, max_evals: int,
                        max_turns: int) -> None:
    """Generate the HELIX project layout in work_dir."""
    work_dir.mkdir(parents=True, exist_ok=True)

    (work_dir / "helix.toml").write_text(HELIX_TOML_TEMPLATE.format(
        max_gens=max_gens, max_evals=max_evals, max_turns=max_turns,
    ))
    (work_dir / "evaluate.py").write_text(EVALUATE_PY_TEMPLATE.format(
        adapter_dir=adapter_dir,
    ))
    (work_dir / "problem.json").write_text(json.dumps({
        "track": track,
        "problem_id": problem_id,
        "unbounded": True,
        "backend": "docker",
    }, indent=2))
    (work_dir / "solve.cpp").write_text(SEED_SOLVE_CPP)

    # HELIX requires a git repo (it uses worktrees).
    if not (work_dir / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=work_dir, check=True)
        subprocess.run(["git", "add", "-A"], cwd=work_dir, check=True)
        subprocess.run(["git", "-c", "user.email=x@x", "-c", "user.name=x",
                        "commit", "-q", "-m", "init"], cwd=work_dir, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="algorithmic", choices=["algorithmic", "research"])
    ap.add_argument("--problem", required=True)
    ap.add_argument("--max-generations", type=int, default=5)
    ap.add_argument("--max-evaluations", type=int, default=20)
    ap.add_argument("--max-turns", type=int, default=10,
                    help="Max agent turns per mutation")
    args = ap.parse_args()

    # Sanity checks on the tunnel + Claude Code.
    for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"):
        if not os.environ.get(var):
            sys.exit(f"Missing env var: {var}. Did you fill in .env?")
    if not shutil.which("claude"):
        sys.exit("Claude Code CLI not found on PATH. Install: "
                 "npm install -g @anthropic-ai/claude-code")
    if not shutil.which("helix"):
        sys.exit("helix CLI not found. Did you `pip install helix-evo`?")

    print(f"Anthropic tunnel: {os.environ['ANTHROPIC_BASE_URL']}")

    # Convert problem id to int when possible (algorithmic uses ints).
    pid = int(args.problem) if args.problem.isdigit() else args.problem

    # Generate the HELIX project at results/helix-<track>-<problem>-<ts>/
    results_root = pathlib.Path(os.environ.get("RESULTS_DIR", "./results"))
    work_dir = results_root / f"helix-{args.track}-{args.problem}-{int(time.time())}"
    adapter_dir = str(pathlib.Path(__file__).parent.resolve())
    setup_helix_project(
        work_dir, track=args.track, problem_id=pid, adapter_dir=adapter_dir,
        max_gens=args.max_generations, max_evals=args.max_evaluations,
        max_turns=args.max_turns,
    )
    print(f"HELIX project: {work_dir}")

    # Hand off to helix evolve. We run it as a subprocess so the env vars
    # (ANTHROPIC_BASE_URL etc.) propagate cleanly to Claude Code subprocesses.
    env = os.environ.copy()
    rc = subprocess.call(["helix", "evolve"], cwd=work_dir, env=env)
    if rc != 0:
        print(f"helix evolve exited with code {rc}", file=sys.stderr)
        return rc

    # Show what got produced.
    subprocess.call(["helix", "frontier"], cwd=work_dir, env=env)
    subprocess.call(["helix", "best", "--export", str(work_dir / "best")],
                    cwd=work_dir, env=env)
    print(f"\nBest candidate: {work_dir / 'best' / 'solve.cpp'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
