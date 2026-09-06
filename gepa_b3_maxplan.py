#!/usr/bin/env python3
"""GEPA on the B3 refactoring tasks at MATCHED conditions with the HELIX arms.

The B3 comparison in the draft comes from gepa_b3_perfile.py, which sets
reflection_lm='claude-opus-4-5-20251101' -- a model string GEPA resolves over
LiteLLM with an API key. So the reported "HELIX 1.00 vs GEPA 0.40" compared
Max-plan Sonnet HELIX against Opus-via-API GEPA. That is not a controlled
comparison, and it is the last unmatched cell in the strongest result we have.

This runs GEPA through the Max-plan CLI callable instead, holding fixed:
    backbone     sonnet (= the HELIX B3 arms)
    budget       max_metric_calls=20 (= HELIX max_evaluations=20)
    evaluator    the same pytest suite, scored as fraction passing
    seed         the same source files

Two GEPA variants, because they differ in how much of the task they can even see:
  per-file      optimises ONE file; the task's coupling spans 3-4 modules, so it
                is structurally unable to fix call sites it cannot edit.
  concatenated  all files joined into one artifact, split back out on write --
                the stronger and fairer GEPA baseline.

    python3 gepa_b3_maxplan.py concat
    python3 gepa_b3_maxplan.py perfile
"""
from __future__ import annotations
import json, pathlib, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "maxplan"))
from claude_cli_lm import ClaudeCLILanguageModel          # noqa: E402
from gepa.optimize_anything import (                       # noqa: E402
    optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig)

B3 = pathlib.Path.home() / "Documents/Research/KDKC/b3_tasks"
TASKS = {
    "b3_1_api_versioning":     ["core.py", "handlers.py", "logger.py", "serializer.py"],
    "b3_2_config_refactor":    ["auth.py", "config.py", "database.py", "logger.py"],
    "b3_3_enum_migration":     ["report.py", "status.py", "user.py", "validator.py"],
    "b3_4_typed_dict":         ["storage.py", "user_service.py", "user_types.py"],
    "b3_5_module_restructure": ["analyzer.py", "core.py", "pipeline.py", "utils.py"],
}
SEP = "\n# ===== FILE: {} =====\n"


def score(work: pathlib.Path) -> float:
    """Fraction of the pytest suite passing -- the same metric the HELIX arms use."""
    try:
        r = subprocess.run(["uv", "run", "--no-project", "--python", "3.12", "--with", "pytest",
                            "python3", "-m", "pytest", "test_refactoring.py", "-q"],
                           cwd=work, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return 0.0
    out = r.stdout + r.stderr
    p = f = 0
    for line in out.splitlines():
        low = line.lower()
        if " passed" in low or " failed" in low:
            for tok, kind in ((" passed", "p"), (" failed", "f")):
                if tok in low:
                    i = low.index(tok)
                    num = low[:i].split()[-1] if low[:i].split() else ""
                    if num.isdigit():
                        if kind == "p": p = max(p, int(num))
                        else: f = max(f, int(num))
    return p / (p + f) if (p + f) else 0.0


def run_task(task: str, files: list[str], mode: str, lm) -> dict:
    src = B3 / task
    targets = files if mode == "concat" else files[:1]

    def make_seed() -> str:
        if mode == "concat":
            return "".join(SEP.format(f) + (src / f).read_text() for f in files)
        return (src / targets[0]).read_text()

    def evaluate(candidate: str) -> float:
        work = pathlib.Path(tempfile.mkdtemp())
        try:
            for f in files + ["test_refactoring.py"]:
                if (src / f).exists():
                    shutil.copy(src / f, work / f)
            if mode == "concat":
                cur, buf = None, []
                for line in candidate.splitlines(keepends=True):
                    if line.startswith("# ===== FILE: "):
                        if cur: (work / cur).write_text("".join(buf))
                        cur, buf = line.split("FILE: ")[1].split(" =====")[0].strip(), []
                    else:
                        buf.append(line)
                if cur: (work / cur).write_text("".join(buf))
            else:
                (work / targets[0]).write_text(candidate)
            return score(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    t0 = time.time()
    res = optimize_anything(
        seed_candidate=make_seed(),
        evaluator=evaluate,
        objective=(f"Fix all failing tests in test_refactoring.py. The change spans "
                   f"{len(files)} modules; find every call site before editing."),
        config=GEPAConfig(
            engine=EngineConfig(max_metric_calls=20),      # = HELIX max_evaluations=20
            reflection=ReflectionConfig(reflection_lm=lm), # Max-plan callable, no API key
        ),
    )
    # GEPAResult in this version exposes no .best_score; the per-objective
    # aggregate subscores are the scored values.
    subs = getattr(res, "val_aggregate_subscores", None) or []
    flat = []
    for x in subs:
        if isinstance(x, (int, float)): flat.append(float(x))
        elif isinstance(x, (list, tuple)): flat += [float(y) for y in x if isinstance(y, (int, float))]
    best = max(flat) if flat else None
    return {"task": task, "mode": mode, "best": best,
            "candidates": getattr(res, "num_candidates", None),
            "metric_calls": getattr(res, "total_metric_calls", None),
            "minutes": round((time.time() - t0) / 60, 1)}


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "concat"
    assert mode in ("concat", "perfile")
    lm = ClaudeCLILanguageModel(model="sonnet", max_turns=1)
    out = pathlib.Path(__file__).parent / f"gepa_b3_maxplan_{mode}.json"
    results = json.loads(out.read_text()) if out.exists() else []
    done = {r["task"] for r in results}
    for task, files in TASKS.items():
        if task in done:
            continue
        try:
            r = run_task(task, files, mode, lm)
        except Exception as e:
            r = {"task": task, "mode": mode, "best": None, "error": str(e)[:300]}
        results.append(r)
        out.write_text(json.dumps(results, indent=2))
        print(f"  {task:<26} {mode:<8} best={r.get('best')}  {r.get('error','')}", flush=True)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
