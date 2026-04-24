import pathlib, json, statistics
from datetime import datetime

# Only show runs with active processes or recently modified
ACTIVE_RUNS = [
    "gepa-algorithmic-qwen3-coder_x_qwen3-coder-20260424_161543",
    "gepa-algorithmic-gpt-oss-120b_x_gpt-oss-120b-20260424_191415",
    "gepa-algorithmic-gemma-4-31b-it_x_gemma-4-31b-it-20260424_192439",
]

print(f"{'='*65}")
print(f"Progress — {datetime.now().strftime('%H:%M:%S')}")
print(f"{'='*65}\n")

for run_name in ACTIVE_RUNS:
    run_dir = pathlib.Path("results") / run_name
    if not run_dir.exists():
        print(f"  {run_name}: NOT FOUND\n")
        continue

    cfg = json.loads((run_dir / "run_config.json").read_text())
    model = cfg.get("task_model", "?").split("/")[-1]

    completed = [json.loads(p.read_text()) for p in run_dir.rglob("result.json")]
    progress = [json.loads(p.read_text()) for p in run_dir.rglob("progress.json")]
    ok = [r for r in completed if r.get("status") == "ok"]
    running = [p for p in progress if p.get("status") == "running"]
    scores = [r["best_score"] for r in ok]

    print(f"  {model}")
    print(f"  done: {len(ok)}/172  running: {len(running)}")
    if scores:
        solves = sum(1 for s in scores if s > 0)
        print(f"  mean={statistics.mean(scores):.2f}  max={max(scores):.2f}  solves={solves}/{len(ok)}")
    best = sorted([p for p in running if p.get("best_score", 0) > 0], key=lambda x: -x["best_score"])[:3]
    if best:
        items = [(p["problem_id"], round(p["best_score"], 1), p["eval_count"]) for p in best]
        print(f"  best in-progress: {items}")
    print()
