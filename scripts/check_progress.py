import pathlib, json, re, statistics
from datetime import datetime

HELIX_RUN = "helix-algorithmic-sonnet_x_qwen3-coder_x_qwen3-coder-20260429_173259"

GEPA_RUNS = [
    "gepa-algorithmic-qwen3-coder_x_qwen3-coder-20260424_161543",
    "gepa-algorithmic-sonnet_x_claude-sonnet-4.6_x_claude-sonnet-4.6-20260429_143406",
    "gepa-algorithmic-gpt-oss-120b_x_gpt-oss-120b-20260424_191415",
    "gepa-algorithmic-gemma-4-31b-it_x_gemma-4-31b-it-20260424_192439",
]

print(f"{'='*65}")
print(f"Progress — {datetime.now().strftime('%H:%M:%S')}")
print(f"{'='*65}\n")

# HELIX
run_dir = pathlib.Path("results") / HELIX_RUN
if run_dir.exists():
    done, running_best = [], []
    for p in sorted(run_dir.iterdir()):
        if not p.is_dir() or not p.name.isdigit(): continue
        r = p / "result.json"
        log = p / "helix_stdout.log"
        if r.exists():
            d = json.loads(r.read_text())
            if d["status"] in ("ok","skipped"): done.append(d["best_score"])
        elif log.exists():
            scores = re.findall(r'"score":\s*([\d.]+)', log.read_text())
            best = max(float(s) for s in scores) if scores else 0
            running_best.append((p.name, best))
    print(f"  [HELIX] claude-sonnet-4-6")
    print(f"  done: {len(done)}/172  running: {len(running_best)}")
    if done:
        solves = sum(1 for s in done if s > 0)
        print(f"  mean={statistics.mean(done):.2f}  median={statistics.median(done):.2f}  max={max(done):.2f}  solves={solves}/{len(done)}")
    best3 = sorted([(p,s) for p,s in running_best if s>0], key=lambda x:-x[1])[:3]
    if best3: print(f"  best running: {best3}")
    print()

# GEPA
for run_name in GEPA_RUNS:
    run_dir = pathlib.Path("results") / run_name
    if not run_dir.exists(): continue
    cfg = json.loads((run_dir/"run_config.json").read_text())
    model = cfg.get("task_model","?").split("/")[-1]
    results = [json.loads(p.read_text()) for p in run_dir.rglob("result.json")]
    progress = [json.loads(p.read_text()) for p in run_dir.rglob("progress.json")]
    done = [r for r in results if r["status"] in ("ok","skipped")]
    running = [p for p in progress if p.get("status") == "running"]
    scores = [r["best_score"] for r in done]
    print(f"  [GEPA] {model}")
    print(f"  done: {len(done)}/172  running: {len(running)}")
    if scores:
        solves = sum(1 for s in scores if s > 0)
        print(f"  mean={statistics.mean(scores):.2f}  median={statistics.median(scores):.2f}  max={max(scores):.2f}  solves={solves}/{len(done)}")
    print()
