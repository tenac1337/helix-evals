#!/usr/bin/env python3
"""GEPA on the same benchmark, backbone and budget as HELIX -- Max plan, no API key.

Purpose: decide which claim the paper can make about the evaluator exploits HELIX
found. If GEPA on the SAME model does not find them, the finding is a capability
result about agentic mutation. If GEPA finds them too, it is a critique of the
benchmark suite. Right now only the second is supported.

    python3 gepa_vs_helix.py --task prism --iters 20
"""
from __future__ import annotations
import argparse, json, os, pathlib, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from claude_cli_lm import ClaudeCLILanguageModel

KDKC = pathlib.Path.home() / "Documents/Research/KDKC"
BENCH = KDKC / "helix-skydiscover-bench"
TASKS = {
    "prism": dict(dir="benchmarks/ADRS/prism", deps=["numpy"],
                  entry="compute_model_placement"),
    "signal_processing": dict(dir="benchmarks/math/signal_processing",
                              deps=["numpy","scipy"], entry="run_signal_processing"),
}

def make_evaluator(eval_dir, deps, workdir):
    """Score a candidate program by running the benchmark's own evaluator."""
    def evaluate(candidate, *a, **kw):
        text = candidate if isinstance(candidate, str) else next(iter(candidate.values()))
        (workdir/"solution.py").write_text(text)
        (workdir/"helix_batch.json").write_text('["0"]')
        cmd = ["uv","run","--no-project","--python","3.12"]
        for d in deps: cmd += ["--with", d]
        cmd += ["python3","helix_eval.py","--eval-dir",str(eval_dir),
                "--program","solution.py","--timeout","400","--raw-metric","combined_score"]
        try:
            out = subprocess.run(cmd, cwd=workdir, capture_output=True,
                                 text=True, timeout=600).stdout
            line = next(l for l in out.splitlines() if l.startswith("HELIX_RESULT="))
            score, side = json.loads(line[len("HELIX_RESULT="):])[0]
            # GEPA requires side_info to be a mapping, not a string.
            return float(score), {"scores": side.get("scores", {})}
        except Exception as e:
            return 0.0, {"error": str(e)[:300]}
    return evaluate

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="prism", choices=sorted(TASKS))
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    spec = TASKS[args.task]
    task_dir = KDKC/"skydiscover"/spec["dir"]
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"gepa_{args.task}_"))
    shutil.copy(BENCH/"helix_eval.py", work/"helix_eval.py")
    seed = (task_dir/"initial_program.py").read_text()

    lm = ClaudeCLILanguageModel(model=args.model, max_turns=1, verbose=True)
    evaluate = make_evaluator(task_dir/"evaluator", spec["deps"], work)

    base, _ = evaluate(seed)
    print(f"seed score: {base}")

    from gepa.optimize_anything import (optimize_anything, GEPAConfig,
                                        EngineConfig, ReflectionConfig)
    # Budget and LM live inside config, not as top-level kwargs.
    cfg = GEPAConfig(
        engine=EngineConfig(max_metric_calls=args.iters,
                            display_progress_bar=False,
                            raise_on_exception=False),
        reflection=ReflectionConfig(reflection_lm=lm),
    )
    t0 = time.time()
    result = optimize_anything(
        seed_candidate=seed,
        evaluator=evaluate,
        objective=(f"Improve {spec['entry']} in this Python program to maximise the "
                   f"evaluator's combined_score. Return the complete program."),
        config=cfg,
    )
    wall = time.time() - t0
    best = getattr(result, "best_candidate", None) or seed
    best_text = best if isinstance(best, str) else next(iter(best.values()))
    best_score, _ = evaluate(best_text)

    outdir = pathlib.Path(args.out or (pathlib.Path(__file__).parent/f"gepa_{args.task}"))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir/"best_solution.py").write_text(best_text)
    (outdir/"summary.json").write_text(json.dumps({
        "task": args.task, "model": args.model, "iters": args.iters,
        "seed_score": base, "best_score": best_score,
        "llm_calls": lm.calls, "wall_seconds": round(wall,1)}, indent=2))
    print(f"\nGEPA {args.task}: seed {base} -> best {best_score}  "
          f"({lm.calls} LLM calls, {wall/60:.1f} min)")
    print(f"wrote {outdir}/best_solution.py  -- run check_integrity-style inspection on it")

if __name__ == "__main__":
    sys.exit(main())
