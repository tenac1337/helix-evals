#!/usr/bin/env python3
"""GEPA on the REAL-repository refactoring tasks, matched to the HELIX arms.

The existing head-to-head (HELIX 5/5, GEPA 1/5) runs on B3 tasks of 30-83 LOC.
This repeats it on cloned upstream projects -- tenacity (1.7k LOC, call sites in
10 modules) and boltons (13.5k LOC) -- so the comparison is not open to the
"toy tasks" objection that applies to B3.

Held identical to the HELIX arms: sonnet backbone on the Max plan (no API key),
20 evaluations, the repo's own pytest suite as the metric, same seed state.

GEPA optimises a single artifact, so the whole package is concatenated into one
document and split back out on write. That is the STRONGER GEPA variant -- the
per-file variant cannot edit call sites in modules it never sees, which on a
10-module refactor would guarantee failure for a structural reason rather than a
capability one.
"""
from __future__ import annotations
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "maxplan"))
from claude_cli_lm import ClaudeCLILanguageModel                      # noqa: E402
from gepa.optimize_anything import (                                   # noqa: E402
    optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig)

BIG = pathlib.Path.home() / "Documents/Research/KDKC/b3_tasks/big"
TASKS = {
    "tenacity_retrystate":         dict(pkg="tenacity", parent="", deps=["pytest","tornado","trio"]),
    "tenacity_stop_after_attempt": dict(pkg="tenacity", parent="", deps=["pytest","tornado","trio"]),
    "boltons_cachedproperty":      dict(pkg="boltons",  parent="", deps=["pytest"]),
}
SEP = "\n# ===== FILE: {} =====\n"


def score_dir(work: pathlib.Path, deps: list[str], parent: str) -> float:
    cmd = ["uv","run","--no-project","--python","3.12"]
    for d in deps: cmd += ["--with", d]
    cmd += ["python3","-m","pytest","-q","--no-header","-p","no:randomly"]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(work / parent) if parent else str(work)
    try:
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=900, env=env)
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 0.0
    p = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    f = int(m.group(1)) if (m := re.search(r"(\d+) (?:failed|error)", out)) else 0
    return p / (p + f) if (p + f) else 0.0


def run_task(name: str, spec: dict, lm) -> dict:
    src = BIG / f"{name}__t20"
    pkg = src / spec["pkg"]
    files = sorted(p.relative_to(src) for p in pkg.rglob("*.py") if "test" not in p.name)

    seed = "".join(SEP.format(f) + (src / f).read_text(errors="replace") for f in files)

    def evaluate(cand: str) -> float:
        work = pathlib.Path(tempfile.mkdtemp())
        try:
            shutil.copytree(src, work / "r", ignore=shutil.ignore_patterns(".helix",".git","__pycache__"))
            w = work / "r"
            cur, buf = None, []
            for line in cand.splitlines(keepends=True):
                if line.startswith("# ===== FILE: "):
                    if cur:
                        t = w / cur; t.parent.mkdir(parents=True, exist_ok=True)
                        t.write_text("".join(buf))
                    cur, buf = line.split("FILE: ")[1].split(" =====")[0].strip(), []
                else: buf.append(line)
            if cur:
                t = w / cur; t.parent.mkdir(parents=True, exist_ok=True); t.write_text("".join(buf))
            return score_dir(w, spec["deps"], spec["parent"])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    t0 = time.time()
    res = optimize_anything(
        seed_candidate=seed, evaluator=evaluate,
        objective=("Make the existing test suite pass. A symbol was renamed in the tests "
                   "but not in the package source; migrate the source. Call sites span "
                   "multiple modules."),
        config=GEPAConfig(engine=EngineConfig(max_metric_calls=20),
                          reflection=ReflectionConfig(reflection_lm=lm)))
    subs = getattr(res, "val_aggregate_subscores", None) or []
    flat = []
    for x in subs:
        if isinstance(x,(int,float)): flat.append(float(x))
        elif isinstance(x,(list,tuple)): flat += [float(y) for y in x if isinstance(y,(int,float))]
    return {"task": name, "best": max(flat) if flat else None,
            "seed_files": len(files), "seed_chars": len(seed),
            "metric_calls": getattr(res,"total_metric_calls",None),
            "minutes": round((time.time()-t0)/60,1)}


def main() -> int:
    lm = ClaudeCLILanguageModel(model="sonnet", max_turns=1)
    out = pathlib.Path(__file__).parent / "gepa_big_maxplan.json"
    results = json.loads(out.read_text()) if out.exists() else []
    done = {r["task"] for r in results}
    for name, spec in TASKS.items():
        if name in done: continue
        try: r = run_task(name, spec, lm)
        except Exception as e: r = {"task": name, "best": None, "error": str(e)[:300]}
        results.append(r); out.write_text(json.dumps(results, indent=2))
        print(f"  {r['task']:<30} best={r.get('best')} {r.get('error','')[:60]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
