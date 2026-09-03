#!/usr/bin/env python3
"""Run AdaEvolve (SkyDiscover's own, current SOTA) on the B3 suite via the Max plan.

Why this exists: the HELIX draft baselines Track B against GEPA, but AdaEvolve,
EvoX, ShinkaEvolve and eps-MemEvo all beat GEPA on every published benchmark, so
"HELIX beats GEPA" does not establish "HELIX beats the state of the art". B3 is
also a benchmark this paper invented -- there is no leaderboard -- which makes the
choice of baseline the whole argument. Running the strongest available one closes
that objection, or tells us early that it does not hold.

Concatenated mode: AdaEvolve is a single-artifact evolver, so the whole project is
presented as one blob with FILE markers and split back out for evaluation. That is
the strongest fair setup for it -- per-file blinds it to the coupling by construction.

Requires claude_openai_proxy.py running (Max plan, no API key).
"""
from __future__ import annotations
import argparse, json, pathlib, re, shutil, subprocess, sys, tempfile, time, urllib.request

B3 = pathlib.Path.home() / "Documents/Research/KDKC/b3_tasks"
SKY = pathlib.Path.home() / "Documents/Research/KDKC/skydiscover"
TASKS = ["b3_1_api_versioning","b3_2_config_refactor","b3_3_enum_migration",
         "b3_4_typed_dict","b3_5_module_restructure"]
SEP = "# ===== FILE: {name} =====\n"

def sources(d):
    return sorted(f for f in d.glob("*.py")
                  if f.name not in {"test_refactoring.py","ablation_guard.py",
                                    "helix_eval.py","evaluate.py"})

def score(tmpdir) -> float:
    r = subprocess.run(["uv","run","--no-project","--python","3.12","--with","pytest",
                        "python3","-m","pytest","test_refactoring.py","--tb=no","-q"],
                       capture_output=True, text=True, cwd=tmpdir, timeout=300)
    out=r.stdout+r.stderr
    p=re.search(r"(\d+) passed",out); f=re.search(r"(\d+) failed",out)
    a=int(p.group(1)) if p else 0; b=int(f.group(1)) if f else 0
    return a/(a+b) if a+b else 0.0

def split_and_score(task_dir, blob):
    with tempfile.TemporaryDirectory() as tmp:
        t=pathlib.Path(tmp)
        for f in task_dir.glob("*.py"):
            shutil.copyfile(f, t/f.name); (t/f.name).chmod(0o644)
        cur,buf=None,[]
        for line in blob.splitlines(keepends=True):
            m=re.match(r"#\s*=====\s*FILE:\s*(\S+)\s*=====",line)
            if m:
                if cur: (t/cur).write_text("".join(buf))
                cur,buf=m.group(1),[]
            elif cur is not None: buf.append(line)
        if cur: (t/cur).write_text("".join(buf))
        try: return score(t)
        except Exception: return 0.0

def proxy_up(base):
    try:
        urllib.request.urlopen(base.rstrip("/")+"/models", timeout=5).read()
        return True
    except Exception:
        return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--api-base", default="http://127.0.0.1:8117/v1")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--task", choices=TASKS)
    a=ap.parse_args()

    if not proxy_up(a.api_base):
        print(f"proxy not reachable at {a.api_base} -- start claude_openai_proxy.py first")
        return 1
    sys.path.insert(0, str(SKY))
    tasks=[a.task] if a.task else TASKS
    out=pathlib.Path(__file__).parent/"adaevolve_b3_results.json"
    results=json.loads(out.read_text()) if out.exists() else []

    for name in tasks:
        d=B3/name
        srcs=sources(d)
        seed="".join(SEP.format(name=f.name)+f.read_text()+"\n" for f in srcs)
        base=split_and_score(d, seed)
        print(f"\n=== AdaEvolve (concatenated): {name}  seed={base:.2f} ===", flush=True)
        t0=time.time()
        best=base; blob=seed
        try:
            from skydiscover.api import run_discovery
            # evaluator receives a program PATH and must return a metrics dict
            def _ev(program_path):
                blob_txt = pathlib.Path(program_path).read_text()
                sc = split_and_score(d, blob_txt)
                return {"combined_score": sc, "solve_rate": sc}
            res = run_discovery(evaluator=_ev, initial_program=seed,
                                search="adaevolve", iterations=a.iters,
                                model=a.model, api_base=a.api_base, cleanup=True)
            blob = getattr(res, "best_program", None) or getattr(res, "best_code", None) or seed
            if not isinstance(blob, str): blob = seed
            best = split_and_score(d, blob)
        except Exception as e:
            print(f"  skydiscover api unavailable ({str(e)[:120]}) -- falling back to CLI")
            with tempfile.TemporaryDirectory() as tmp:
                t=pathlib.Path(tmp); (t/"seed.py").write_text(seed)
                cmd=["uv","run","skydiscover-run",str(t/"seed.py"),
                     "--search","adaevolve","-i",str(a.iters),
                     "--model",a.model,"--api-base",a.api_base]
                r=subprocess.run(cmd,cwd=SKY,capture_output=True,text=True,timeout=5400)
                print("  cli rc:",r.returncode, (r.stderr or "")[-300:])
        print(f"  seed {base:.2f} -> best {best:.2f}  ({(time.time()-t0)/60:.1f} min)", flush=True)
        results=[x for x in results if x.get("task")!=name]+[
            dict(task=name, method="adaevolve-concat", seed_score=base, best_score=best)]
        out.write_text(json.dumps(results,indent=2))
    print(f"\nwrote {out}")
    return 0

if __name__=="__main__":
    sys.exit(main())
