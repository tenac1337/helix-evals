#!/usr/bin/env python3
"""Measure the B2 agent-harness baselines ourselves, on the Max plan.

Same motivation as verify_b3_baselines.py: the draft's B2 comparison cites
diff-only at 0.30 and HELIX at 1.00, but only HELIX's side was ever verified
against run state. B2 is one of the strongest remaining wins, so its baseline
gets measured rather than quoted.

B2's evaluator scores the fraction of 10 agent tasks solved -- discrete, no
normaliser, no direction ambiguity, nothing to forge.
"""
from __future__ import annotations
import argparse, json, pathlib, re, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).parent / "maxplan"))
sys.path.insert(0, str(pathlib.Path.home() / "Documents/Research/KDKC/gepa"))
from claude_cli_lm import ClaudeCLILanguageModel

TASK = pathlib.Path.home() / "Documents/Research/KDKC/b3_tasks/b2_agent_harness"
TARGET = "agent.py"          # the single file a per-file baseline may edit
SEP = "\n# ===== FILE: {name} =====\n"

def sources():
    return sorted(f for f in TASK.glob("*.py")
                  if f.name not in {"evaluate.py", "ablation_guard.py", "helix_eval.py"})

def score_dir(d) -> float:
    r = subprocess.run(["uv","run","--no-project","--python","3.12","python3","evaluate.py"],
                       capture_output=True, text=True, cwd=d, timeout=300)
    for line in reversed((r.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return float(json.loads(line).get("score", 0.0))
            except Exception:
                continue
    return 0.0

def make_eval(mode):
    def evaluate(candidate, *a, **kw):
        text = candidate if isinstance(candidate, str) else next(iter(candidate.values()))
        with tempfile.TemporaryDirectory() as tmp:
            t = pathlib.Path(tmp)
            for f in TASK.glob("*.py"):
                shutil.copyfile(f, t / f.name)
                (t / f.name).chmod(0o644)
            if mode == "per-file":
                (t / TARGET).write_text(text)
            else:
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
                return score_dir(t), {"mode": mode}
            except Exception as e:
                return 0.0, {"error": str(e)[:200]}
    return evaluate

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()

    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig
    out, results = pathlib.Path(__file__).parent / "b2_baseline_results.json", []
    for mode in ("per-file", "concatenated"):
        srcs = sources()
        seed = ((TASK / TARGET).read_text() if mode == "per-file"
                else "".join(SEP.format(name=f.name) + f.read_text() for f in srcs))
        lm = ClaudeCLILanguageModel(model=a.model, max_turns=1)
        ev = make_eval(mode)
        base, _ = ev(seed)
        obj = ("Integrate the Planner into the Agent harness so all 10 task types are solved. "
               + (f"You may only edit {TARGET}." if mode == "per-file"
                  else "The program is all project files concatenated with "
                       "'# ===== FILE: name =====' markers; return the whole thing."))
        print(f"\n=== GEPA-OA {mode}: b2_agent_harness (seed {base:.2f}) ===", flush=True)
        t0 = time.time()
        try:
            res = optimize_anything(seed_candidate=seed, evaluator=ev, objective=obj,
                config=GEPAConfig(engine=EngineConfig(max_metric_calls=a.iters,
                                                     display_progress_bar=False,
                                                     raise_on_exception=False),
                                  reflection=ReflectionConfig(reflection_lm=lm)))
            best = getattr(res, "best_candidate", None) or seed
            bt = best if isinstance(best, str) else next(iter(best.values()))
            sc, _ = ev(bt)
        except Exception as e:
            sc = base; print(f"  GEPA failed: {e}")
        print(f"  seed {base:.2f} -> best {sc:.2f}  ({lm.calls} calls, {(time.time()-t0)/60:.1f} min)", flush=True)
        results.append(dict(task="b2_agent_harness", mode=mode, seed_score=base,
                            best_score=sc, llm_calls=lm.calls))
        out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}")

if __name__ == "__main__":
    sys.exit(main())
