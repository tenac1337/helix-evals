# Results reconciliation — HELIX draft vs. run state on disk

Audit date: 2026-08-29. Reproduce with `python3 verify_paper_numbers.py`.

> **Superseded in part, 2026-09-03.** This document checks whether draft numbers
> match run state. It does *not* check whether the run state was honestly
> produced. A later integrity pass (`EVALUATOR_INTEGRITY.md`) found that the two
> B1 tasks were won by evaluator exploits — a forged `perf_counter`, results
> precomputed outside the timed region, and a model whose `__len__` returned 0 so
> the training loop never executed. **Both B1 tasks are cut.** §2 and §5 below are
> retained as a record of the earlier audit; do not take numbers from them.
> Current claimable set: `verify_all_claims.py`.

**10 of 12 checkable claims verify. Two Track B cells do not, and Table 5 has no
supporting run directories at all.** None of this weakens the paper's thesis —
the corrected margins are still overwhelming — but every number below has to be
either corrected or removed before submission, because a reviewer who reruns
`b1_lru_graph` gets 5.76M, not 8.1M.

---

## 1. Verified — no action

| Claim | Draft | Disk | Evidence |
|---|---|---|---|
| Can't Be Late | 82.33% | 0.8233 | 25 generations, 11 candidates |
| ARC-AGI agent | 90.0% | 0.9000 | 20 generations, 11 candidates |
| AIME 2025 | 51.11% | 0.5111 | 20 generations, 4 candidates |
| Circle packing n=26 | 2.6360 | 2.6360 | 30 generations |
| B2 agent harness | 1.00 | 1.00 | 0.10 → 1.00 |
| B3.1–B3.5 refactor | 1.00 each | 1.00 each | 5/5 tasks |

The B3 suite is the strongest evidence in the paper and it is fully backed:
GEPA-OA per-file 0.31, concatenated 0.48, HELIX 1.00 across all five tasks.

---

## 2. Corrections required — Table 4

### B1 LRU+graph: 8.1M → 5,761,342

No run on disk produced 8.1M. The only `b1_lru_graph` run (May 5, preserved as
`.helix/state 2.json` after a failed 2026-05-15 re-run overwrote `state.json`)
peaked at **5,761,342** on candidate `g4-s4`:

```
g0-s0      86,052.53      (seed)
g2-s2   5,318,261.12
g4-s4   5,761,342.44      <- best
g5-s5   5,758,709.78
g10-s10 5,676,499.25
```

The win survives comfortably:

| Baseline | Corrected margin |
|---|---|
| GEPA-OA per-file (100K) | **57.6×** |
| GEPA-OA concatenated (422K) | **13.7×** |

Change "8.1M" to "5.76M" in Table 4 and the §5.2 prose (">10,000×" against the
~800 qps baseline becomes ~7,200×).

### B1 ML loop: 5.7M → 6,671,604

The draft **understates** this result. Best candidate is `g10-s10` at
**6,671,604**, not the 5.7M reported (which appears to be `g6-s6`, 5,714,286 —
likely the last frontier entry rather than the maximum).

This matters: at 6.67M vs the diff-only baseline's 6.7M, the only cell in Track B
where a baseline beats HELIX becomes a **statistical tie (0.996×)** rather than a
loss. Against GEPA-OA per-file (814K) it is an 8.2× win.

---

## 3. Table 5 has no supporting runs

Table 5's grid is 4 columns (B1 inf-opt, B1 LRU+gr, B1 ML loop, B2 harness) × 6
rows. **No ablation directory exists for any of those four columns.** The only
ablation directories on disk are `b3_1_api_versioning_{t1,singlefile}` and
`b3_3_enum_migration_{t1,singlefile}` — B3 tasks, which are discussed in §5.3
prose but are not Table 5 columns.

Those four B3 directories had never been run (no `state.json`) and their configs
could not load against the current HELIX schema — they used the removed
`allowed_tools`, `[scope]`, and `evaluator`-as-string fields. They have been
regenerated and staged; run with `b3_tasks/run_ablations.sh`.

### An internal inconsistency the correction exposes

Table 5 reports the **no-shell** ablation on B1 LRU+graph at **7.5M** and
**single-file** at 6.6M. With the full configuration corrected to 5.76M, both
ablations would *exceed* the full system — i.e. the table would say removing
tools makes HELIX better, contradicting §5.3's claim that "the full configuration
dominates across the board."

So the 8.1M and the 7.5M come from the same unlocated run family. Either recover
that run, or regenerate the whole B1 LRU+graph column together. **Do not correct
the full-config cell while leaving the ablation cells untouched** — that ships a
table that argues against the paper's own thesis.

---

## 4. No local data

**B1 inference-opt (6.9×, 538 → 3,714 tok/s).** Nothing on this machine records
it. `helix-inference-opt/experiments.tsv` is a different, earlier experiment
(42.4 → 96.3 tok/s, ≈2.3×), and `helix-inference-opt-multifile.zip` contains
source files only, no `.helix` state. The task needs CUDA, so this was almost
certainly run on a GPU host. Recover it from there or cut the cell.

**Track C.** The one HELIX Frontier-CS run (`20260508_153525`) is null: 172
problems, zero LLM calls, every score 0, recorded as `n_ok: 172, n_error: 0`.
`core/results_aggregator.py` now detects this and refuses to report it. The
earlier May/June runs from the feasibility study (30/86 solved, mean 23.37) lose
to every published baseline — GEPA ~51.3, AdaEvolve/EvoX 62.6 — so Track C should
be reported as a cost-normalized subset with unique-win counts, per §5.5, not as
a leaderboard comparison.

---

## 5. What is claimable today — SUPERSEDED, see note at top

The table below was correct as a *reproducibility* check on 2026-08-29 and is
wrong as a *results* claim. The two B1 rows are exploits and are cut; run
`verify_all_claims.py` for the integrity-filtered set.

Five benchmarks beating GEPA-OA, every cell backed by run state:

| Benchmark | Best baseline | HELIX | Margin |
|---|---|---|---|
| B3 refactor (5 tasks) | 0.48 (concatenated) | **1.00** | solves all 5; per-file solves 0 |
| B2 agent harness | 0.30 (diff-only) | **1.00** | 3.3× |
| ~~B1 LRU+graph~~ | ~~422K (concatenated)~~ | ~~**5.76M**~~ | **CUT — evaluator exploit** |
| Can't Be Late | 7.8% (GEPA-OA) | **82.33%** | 10.6× |
| ARC-AGI agent | 89.5% (GEPA-OA) | **90.0%** | + 0.5 pts |

That meets the submission bar. The work remaining is making Table 4 and Table 5
consistent with it.
