#!/usr/bin/env python3
"""HELIX <-> GSO adapter.

GSO gives an agent a real codebase plus a performance test, and asks it to match
an expert developer's optimization commit. That is repo-scale, multi-file work --
HELIX's actual thesis -- and unlike the AlphaEvolve math problems it is scored on
a public leaderboard against models we can run on the Max plan.

Design: HELIX runs OUTSIDE the container on a checkout of the repo; the evaluator
shells INTO the container to time the performance test against the mounted
worktree. That keeps HELIX's normal git-worktree mutation loop intact and avoids
installing a coding-agent CLI inside 102 task images.

  prepare  -- extract the repo at base_commit from the task image
  evaluate -- run the task's OWN tests in the container, report speedup vs base
  export   -- turn the winning worktree into GSO's prediction jsonl

Two corrections learned the hard way, recorded so they are not repeated:

1. The images use a uv venv at /testbed/.venv, NOT conda. There is no `testbed`
   conda env (that pattern is SWE-bench's).

2. `prob_script` is the SPECIFICATION SHOWN TO THE AGENT, not the thing executed.
   It is authored in Python 3.12 syntax (PEP 701 nested f-string quotes) while the
   task venvs are as old as Python 3.9, so running it directly is a SyntaxError.
   The `tests` field holds the scripts GSO actually times.

Scoring stays with GSO's own harness (src/gso/harness/opt_at_k.py): it runs the
tests before the patch, applies it, reinstalls, runs after, then resets and runs
main -- and applies the >=95%-of-human-speedup threshold plus correctness. We only
produce the prediction jsonl; we do not reimplement Opt@1.
"""
from __future__ import annotations

import argparse, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time

IMG = "slimshetty/gso:gso.eval.x86_64.{iid}"
PLATFORM = "linux/amd64"          # all 102 tasks are x86_64


def docker(*args, timeout=1800, **kw):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout, **kw)


def load_task(iid: str) -> dict:
    from datasets import load_dataset
    ds = load_dataset("gso-bench/gso", split="test")
    for r in ds:
        if r["instance_id"] == iid:
            return r
    raise SystemExit(f"unknown instance_id {iid}")


def prepare(iid: str, dest: pathlib.Path) -> dict:
    """Extract /testbed from the task image into a git repo HELIX can mutate."""
    task = load_task(iid)
    img = IMG.format(iid=iid.lower())
    if not docker("image", "inspect", img, timeout=120).returncode == 0:
        print(f"pulling {img} ...", flush=True)
        p = docker("pull", "--platform", PLATFORM, img, timeout=3600)
        if p.returncode != 0:
            raise SystemExit(f"pull failed: {p.stderr[-300:]}")

    dest.mkdir(parents=True, exist_ok=True)
    cid = docker("create", "--platform", PLATFORM, img, timeout=300).stdout.strip()
    try:
        subprocess.run(f"docker cp {cid}:/testbed/. {dest}/", shell=True, check=True,
                       capture_output=True, timeout=1800)
    finally:
        docker("rm", "-f", cid, timeout=120)

    # prob_script is the agent-facing spec (may be 3.12 syntax); tests are what run.
    (dest / "prob_script.py").write_text(task["prob_script"])
    tdir = dest / ".gso_tests"; tdir.mkdir(exist_ok=True)
    for i, t in enumerate(task.get("tests") or []):
        (tdir / f"test_{i}.py").write_text(t)
    (dest / ".gso_task.json").write_text(json.dumps(
        {k: task[k] for k in ("instance_id", "repo", "base_commit", "api")}, indent=2))
    # HELIX needs a clean git baseline to diff mutations against
    if not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q", "."], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, capture_output=True)
    subprocess.run(["git", "-c", "user.email=h@h", "-c", "user.name=helix",
                    "commit", "-qm", f"GSO seed {iid}"], cwd=dest, capture_output=True)
    return task


def time_in_container(iid: str, worktree: pathlib.Path, reps: int = 1,
                      eqcheck: bool = False) -> tuple[float, str]:
    """Total time across the task's test scripts, with `worktree` mounted.

    Invocation matches GSO's own harness (evalscript.py RUN_BASE / RUN_PATCH):
        <script> <output.txt> <--reference|--eqcheck> --file_prefix <prefix>
    Each script writes "Execution time: N.NNNNNNs" lines; we take the minimum per
    script (least-noisy sample) and sum across scripts. Parsing happens in Python
    -- doing it in the shell needs three levels of nested quoting and silently
    produced 0.0.
    """
    img = IMG.format(iid=iid.lower())
    worktree = worktree.resolve()   # -v needs an ABSOLUTE source path
    flag = "--eqcheck" if eqcheck else "--reference"
    script = (
        "cd /testbed && source .venv/bin/activate 2>/dev/null\n"
        "for f in .gso_tests/test_*.py; do\n"
        '  i=$(basename "$f" .py)\n'
        f'  python3 "$f" "/tmp/$i.txt" {flag} --file_prefix "gso_$i" >/dev/null 2>&1\n'
        '  echo "===$i==="\n'
        '  cat "/tmp/$i.txt" 2>/dev/null\n'
        "done\n")
    best_total, last = float("inf"), ""
    # Pass the script as a MOUNTED FILE. Handing a multi-line script to
    # `bash -lc` through docker's arg handling silently produced no output.
    # Write the script INTO the worktree, which is already mounted. A separate
    # -v mount from macOS tempdirs (/var/folders/...) is not shared with Docker
    # Desktop, so it mounted empty and bash ran nothing.
    sh = worktree / ".gso_time.sh"
    sh.write_text(script)
    try:
        for _ in range(max(1, reps)):
            p = docker("run", "--rm", "--platform", PLATFORM, "--network", "none",
                       "-v", f"{worktree}:/testbed",
                       img, "bash", "/testbed/.gso_time.sh", timeout=1800)
            out = p.stdout + p.stderr
            last = out[-800:]
            total, found = 0.0, False
            for block in out.split("===")[1:]:
                times = [float(x) for x in
                         re.findall(r"Execution time:\s*([0-9.]+)", block)]
                if times:
                    total += min(times); found = True
            if found:
                best_total = min(best_total, total)
    finally:
        sh.unlink(missing_ok=True)
    return (best_total if best_total != float("inf") else float("inf")), last


def evaluate(iid: str, worktree: pathlib.Path, base_time: float) -> None:
    """HELIX evaluator entry point. Emits the HELIX_RESULT contract."""
    ids = ["0"]
    bf = worktree / "helix_batch.json"
    if bf.exists():
        try: ids = [str(i) for i in (json.loads(bf.read_text()) or ["0"])] or ["0"]
        except json.JSONDecodeError: pass

    t, tail = time_in_container(iid, worktree)
    speedup = (base_time / t) if t and t != float("inf") else 0.0
    side = {"scores": {"combined_score": speedup, "speedup": speedup,
                       "seconds": t if t != float("inf") else -1.0},
            "base_seconds": base_time, "stdout_tail": tail[-600:]}
    print("HELIX_RESULT=" + json.dumps([[speedup, side] for _ in ids]))


def export(iid: str, worktree: pathlib.Path, out: pathlib.Path, model: str) -> None:
    """Emit GSO's prediction jsonl from the evolved worktree."""
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=worktree,
                          capture_output=True, text=True, timeout=300).stdout
    rec = {"instance_id": iid, "model_patch": diff, "model_name_or_path": model}
    with out.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"wrote prediction for {iid} ({len(diff)} bytes of diff) -> {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prepare", "evaluate", "export", "basetime"])
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--dir", type=pathlib.Path, default=pathlib.Path("."))
    ap.add_argument("--base-time", type=float, default=0.0)
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("predictions.jsonl"))
    ap.add_argument("--model", default="helix+claude-opus-4-8")
    a = ap.parse_args()
    a.dir = a.dir.resolve()

    if a.mode == "prepare":
        prepare(a.instance_id, a.dir)
        t, _ = time_in_container(a.instance_id, a.dir)
        (a.dir / ".gso_base_time").write_text(str(t))
        print(f"prepared {a.instance_id} in {a.dir}; base time {t:.3f}s")
    elif a.mode == "basetime":
        t, tail = time_in_container(a.instance_id, a.dir)
        print(f"{t:.6f}")
    elif a.mode == "evaluate":
        bt = a.base_time or float((a.dir / ".gso_base_time").read_text())
        evaluate(a.instance_id, a.dir, bt)
    else:
        export(a.instance_id, a.dir, a.out, a.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
