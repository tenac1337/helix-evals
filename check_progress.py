import pathlib, json, statistics

# Show all runs that have any results
run_dirs = sorted(pathlib.Path("results").iterdir(), key=lambda p: p.name)
active = []
for run_dir in run_dirs:
    results = list(run_dir.rglob("result.json"))
    progress = list(run_dir.rglob("progress.json"))
    if results or progress:
        active.append(run_dir)

print(f"Found {len(active)} runs with data:\n")
for run_dir in sorted(active, key=lambda p: p.stat().st_mtime, reverse=True):
    results = [json.loads(p.read_text()) for p in run_dir.rglob("result.json")]
    progress = [json.loads(p.read_text()) for p in run_dir.rglob("progress.json")]
    ok = [r for r in results if r.get("status") == "ok"]
    running = [p for p in progress if p["status"] == "running"]
    scores = [r["best_score"] for r in ok]
    cfg_path = run_dir / "run_config.json"
    model = json.loads(cfg_path.read_text()).get("task_model","?").split("/")[-1] if cfg_path.exists() else "?"
    print(f"{run_dir.name}")
    print(f"  model={model}  done={len(ok)}/172  running={len(running)}")
    if scores:
        print(f"  mean={statistics.mean(scores):.2f}  max={max(scores):.2f}  solves={sum(1 for s in scores if s>0)}/{len(ok)}")
    print()
