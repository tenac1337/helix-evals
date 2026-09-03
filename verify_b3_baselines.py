#!/usr/bin/env python3
"""Re-run the GEPA-OA baselines on B3 ourselves, on the Max plan (no API key).

Why: every Track B win compares HELIX against baseline numbers taken from the
draft (per-file 0.31, concatenated 0.48, diff-only 0.30). We verified HELIX's
side of those comparisons against run state and found 2 of 12 claims wrong -- we
never verified the baseline side at all. A win is only as good as the number it
beats, so these get measured rather than cited.

Two baselines, matching the draft's definitions:
  per-file      -- GEPA optimises ONE file, blind to the others
  concatenated  -- GEPA sees all files as a single blob and must regenerate it

    python3 verify_b3_baselines.py --task b3_1_api_versioning --mode per-file
    python3 verify_b3_baselines.py --all
"""
from __future__ import annotations
import argparse, json, pathlib, re, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).parent / "maxplan"))
sys.path.insert(0, str(pathlib.Path.home() / "Documents/Research/KDKC/gepa"))
from claude_cli_lm import ClaudeCLILanguageModel

B3 = pathlib.Path.home() / "Documents/Research/KDKC/b3_tasks"
TASKS = {
    "b3_1_api_versioning":     "core.py",
    "b3_2_config_refactor":    "config.py",
    "b3_3_enum_migration":     "status.py",
    "b3_4_typed_dict":         "storage.py",
    "b3_5_module_restructure": "core.py",
}
SEP = "\n# ===== FILE: {name} =====\n"

def sources(task_dir):
    return sorted(f for f in task_dir.glob("*.py")
                  if f.name not in {"test_refactoring.py", "ablation_guard.py",
                                    "helix_eval.py", "evaluate.py"})

def run_tests(tmpdir) -> float:
    r = subprocess.run(["uv","run","--no-project","--python","3.12","--with","pytest",
                        "python3","-m","pytest","test_refactoring.py","--tb=no","-q"],
                       capture_output=True, text=True, cwd=tmpdir, timeout=300)
    out = r.stdout + r.stderr
    p = re.search(r"(\d+) passed", out); f = re.search(r"(\d+) failed", out)
    passed = int(p.group(1)) if p else 0
    failed = int(f.group(1)) if f else 0
    total = passed + failed
    return passed / total if total else 0.0

def make_eval(task_dir, mode, target):
    def evaluate(candidate, *a, **kw):
        text = candidate if isinstance(candidate, str) else next(iter(candidate.values()))
        with tempfile.TemporaryDirectory() as tmp:
            t = pathlib.Path(tmp)
            for f in task_dir.glob("*.py"):
                shutil.copyfile(f, t / f.name)
                (t / f.name).chmod(0o644)
            if mode == "per-file":
                (t / target).write_text(text)
            else:                                   # concatenated: split the blob back out
                cur, buf = None, []
                for line in text.splitlines(keepends=True):
                    m = re.match(r"#\s*=====\s*FILE:\s*(\S+)\s*=====", line)
                    if m:
                        if cur: (t / cur).write_text("".join(buf))
                        cur, buf = m.group(1), []
                    elif cur is not None:
                        buf.append(line)
                if cur: (t / cur).write_text("".join(buf))
            try:
                return run_tests(t), {"mode": mode}
            except Exception as e:
                return 0.0, {"error": str(e)[:200]}
    return evaluate

def run_one(task, mode, iters, model):
    task_dir = B3 / task
    target = TASKS[task]
    srcs = sources(task_dir)
    if mode == "per-file":
        seed = (task_dir / target).read_text()
    else:
        seed = "".join(SEP.format(name=f.name) + f.read_text() for f in srcs)

    lm = ClaudeCLILanguageModel(model=model, max_turns=1)
    ev = make_eval(task_dir, mode, target)
    base, _ = ev(seed)

    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig
    obj = (f"Fix the code so all tests in test_refactoring.py pass. "
           + (f"You may only edit {target}." if mode == "per-file"
              else "The program is all project files concatenated with '# ===== FILE: name =====' "
                   "markers; return the whole thing with the same markers."))
    t0 = time.time()
    try:
        res = optimize_anything(seed_candidate=seed, evaluator=ev, objective=obj,
            config=GEPAConfig(engine=EngineConfig(max_metric_calls=iters,
                                                 display_progress_bar=False,
                                                 raise_on_exception=False),
                              reflection=ReflectionConfig(reflection_lm=lm)))
        best = getattr(res, "best_candidate", None) or seed
        best_text = best if isinstance(best, str) else next(iter(best.values()))
        score, _ = ev(best_text)
    except Exception as e:
        score, best_text = base, f"# GEPA failed: {e}"
    return dict(task=task, mode=mode, seed_score=base, best_score=score,
                llm_calls=lm.calls, wall_s=round(time.time()-t0,1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=sorted(TASKS))
    ap.add_argument("--mode", choices=["per-file","concatenated"], default="per-file")
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    jobs = ([(t,m) for t in TASKS for m in ("per-file","concatenated")] if a.all
            else [(a.task, a.mode)])
    out = pathlib.Path(__file__).parent / "b3_baseline_results.json"
    results = json.loads(out.read_text()) if out.exists() else []
    for t, m in jobs:
        print(f"\n=== GEPA-OA {m}: {t} ===", flush=True)
        r = run_one(t, m, a.iters, a.model)
        print(f"  seed {r['seed_score']:.2f} -> best {r['best_score']:.2f}  "
              f"({r['llm_calls']} calls, {r['wall_s']/60:.1f} min)", flush=True)
        results = [x for x in results if not (x["task"]==t and x["mode"]==m)] + [r]
        out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}")

if __name__ == "__main__":
    sys.exit(main())
