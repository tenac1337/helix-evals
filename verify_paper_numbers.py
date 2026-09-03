#!/usr/bin/env python3
"""Verify every number in the HELIX draft against the run state on disk.

    python3 verify_paper_numbers.py            # table
    python3 verify_paper_numbers.py --json     # machine-readable

Motivation: on 2026-08-29 an audit found that two Track B cells did not match any
run on disk -- B1 lru_graph was reported as 8.1M against a best recorded score of
5.76M, and B1 ml_loop was reported as 5.7M when the best recorded candidate was
6.67M. A separate Track C run had stored 172 problems of zeros as ``n_ok: 172``.
Numbers that cannot be reproduced from run state are the fastest way to lose a
paper, so this check is kept in the repo and run before every submission.

Reads ``.helix/state.json`` for each task and reports the best candidate score
against the value printed in the draft.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

KDKC = pathlib.Path(__file__).resolve().parent.parent

# (draft label, path, draft value, tolerance as fraction, note)
CLAIMS = [
    # ---- Track A (parity) -------------------------------------------------
    ("Can't Be Late",        "helix-evals/cant_be_late",      0.8233, 0.02, "82.33% cost saved"),
    ("ARC-AGI agent",        "helix-evals/arc_agi",           0.9000, 0.02, "90.0% public test acc"),
    ("AIME 2025",            "helix-evals/aime",              0.5111, 0.02, "51.11% accuracy"),
    ("Circle packing n=26",  "helix-evals/circle_packing",    2.6360, 0.01, "sum of radii"),
    # ---- Track B (capability expansion) -----------------------------------
    ("B1 lru_graph",         "b3_tasks/b1_lru_graph",         8.1e6,  0.05, "qps; baseline GEPA-OA concat 422K"),
    ("B1 ml_loop",           "b3_tasks/b1_ml_loop",           5.7e6,  0.05, "sps; baseline diff-only 6.7M"),
    ("B2 agent harness",     "b3_tasks/b2_agent_harness",     1.00,   0.01, "solve rate; baseline diff-only 0.30"),
    ("B3.1 api_versioning",  "b3_tasks/b3_1_api_versioning",  1.00,   0.01, "solve rate"),
    ("B3.2 config_refactor", "b3_tasks/b3_2_config_refactor", 1.00,   0.01, "solve rate"),
    ("B3.3 enum_migration",  "b3_tasks/b3_3_enum_migration",  1.00,   0.01, "solve rate"),
    ("B3.4 typed_dict",      "b3_tasks/b3_4_typed_dict",      1.00,   0.01, "solve rate"),
    ("B3.5 module_restruct", "b3_tasks/b3_5_module_restructure", 1.00, 0.01, "solve rate"),
]


def best_from_state(d: pathlib.Path) -> tuple[float | None, int, int, str | None]:
    """(best score, generations, n candidates, error). Prefers a preserved
    'state 2.json' when a later failed re-run has overwritten 'state.json'."""
    helix = d / ".helix"
    if not helix.exists():
        return None, 0, 0, "no .helix directory"

    candidates = [helix / "state.json", helix / "state 2.json"]
    best_overall, gen_overall, n_overall, seen = None, 0, 0, False
    for st in candidates:
        if not st.exists():
            continue
        seen = True
        try:
            s = json.loads(st.read_text())
        except Exception as exc:
            return None, 0, 0, f"unreadable {st.name}: {exc}"
        iss = s.get("instance_scores") or {}
        best, n = None, 0
        for v in iss.values():
            if isinstance(v, dict):
                nums = [x for x in v.values() if isinstance(x, (int, float))]
                if nums:
                    n += 1
                    m = sum(nums) / len(nums)
                    best = m if best is None else max(best, m)
        if best is not None and (best_overall is None or best > best_overall):
            best_overall, gen_overall, n_overall = best, s.get("generation", 0) or 0, n

    if not seen:
        return None, 0, 0, "no state.json"
    if best_overall is None:
        return None, 0, 0, "no scores recorded"
    if best_overall == 0.0:
        return 0.0, gen_overall, n_overall, "NULL RUN (all scores 0)"
    return best_overall, gen_overall, n_overall, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows, bad = [], 0
    for label, rel, claimed, tol, note in CLAIMS:
        best, gen, n, err = best_from_state(KDKC / rel)
        if best is None:
            status, ok = err or "missing", False
        elif err:
            status, ok = err, False
        elif abs(best - claimed) <= tol * abs(claimed):
            status, ok = "verified", True
        else:
            direction = "OVER-reported" if claimed > best else "UNDER-reported"
            status, ok = f"MISMATCH ({direction} in draft)", False
        if not ok:
            bad += 1
        rows.append(dict(label=label, path=rel, draft=claimed, disk=best,
                         generations=gen, candidates=n, status=status,
                         verified=ok, note=note))

    if args.json:
        print(json.dumps(rows, indent=2))
        return 1 if bad else 0

    print(f"{'CLAIM':<23}{'DRAFT':>13}{'ON DISK':>15}{'gen':>5}{'cand':>6}  STATUS")
    print("-" * 96)
    for r in rows:
        disk = "—" if r["disk"] is None else (
            f"{r['disk']:,.4g}" if r["disk"] < 1000 else f"{r['disk']:,.0f}")
        draft = f"{r['draft']:,.4g}" if r["draft"] < 1000 else f"{r['draft']:,.0f}"
        mark = "  " if r["verified"] else "!!"
        print(f"{mark}{r['label']:<21}{draft:>13}{disk:>15}"
              f"{r['generations']:>5}{r['candidates']:>6}  {r['status']}")

    print("-" * 96)
    print(f"{len(rows) - bad}/{len(rows)} claims verified against run state.")
    if bad:
        print("\nUnverified claims must be corrected or removed before submission:")
        for r in rows:
            if not r["verified"]:
                print(f"  - {r['label']}: draft says {r['draft']:,.6g}, "
                      f"disk says {'nothing' if r['disk'] is None else format(r['disk'], ',.6g')}"
                      f"  [{r['note']}]")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
