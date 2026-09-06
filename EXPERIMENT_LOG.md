# HELIX ICLR 2026 — Complete Experimental Record

*2026-09-03 through 2026-09-05. Companion to `ICLR_DRAFT.md`. The paper reports what survived; this records everything that was tried, what each attempt showed, why things were cut, every bug that produced a wrong number, and what should happen next. Written so Karim can reconstruct any decision without the conversation.*

---

## Part I — Every experiment, in order

### E1. Initial state audit (Sept 3, morning)

**What.** Reconciled every number in the existing draft against `.helix/state.json` on disk.

**Found.** Three of the draft's headline wins were evaluator exploits (see E4). The integrity checker that should have caught them had been silently passing everything (see B1). The B1 systems benchmarks were unusable. Table 5 (ablations) had no supporting runs for any of its four columns.

**Learned.** The reconciliation that had been done earlier verified that numbers matched run state — not that run state was honest. Those are different audits, and only the second one matters.

### E2. Second autocorrelation inequality (B.2) — the apparent headline win

**What.** HELIX on AlphaEvolve problem B.2. Result: 0.9171444 vs AlphaEvolve's published 0.8962799, +2.33%, reached at 16 candidates.

**Verification performed.** Four attacks: (i) evaluator determinism (`sd = 0.0` over 5 repeats); (ii) quadrature exactness — the autoconvolution of a step function is piecewise linear, so L², L¹ and L∞ are all exact, confirmed N-invariant to 1.1 × 10⁻¹⁵ under 16× refinement; (iii) no free lunch from finer N — random functions at N=1000 score no better than N=50 (~0.67 either way); (iv) the evaluator recomputes c₂ from returned values rather than trusting the candidate. Integrity: 7/7 candidates clean, gradual progression. Mechanism visible: AlphaEvolve's seed fixes 50 intervals, HELIX's winner uses 150.

**Then (Sept 4).** Ran AdaEvolve on the same problem, same backbone, same budget. AdaEvolve reached **0.9250655 at iteration 16** (run 1), then **0.9318 verified across 907 evaluations** (run 2). HELIX loses B.2 on the same hardware.

**Learned.** Beating a published number from a different backbone is not beating the field. The parity comparison was the single most important experiment we ran, and it produced a negative result. AdaEvolve's winning program uses multiscale continuation N=50→100→200→400→600 — a legitimately better optimiser than HELIX found.

**Status in paper.** §5.4, reported as a loss against the strongest comparator.

### E3. Protocol budget correction

**What.** Discovered HELIX had been running at `max_evaluations = 40` (20 candidates) while AdaEvolve/EvoX get 100 iterations. We were at 20% of the published protocol.

**Fix.** Raised to 200 evaluations (100 candidates), resumed from the preserved frontier. Snapshotted the 20-candidate state separately so the efficiency claim (beat AlphaEvolve's number at 16% of baseline budget) survives.

**Result.** circle_packing advanced 99.3% → 99.87%; third_autocorr 99.5% → 99.84%. Neither crossed.

**Learned.** "Matched budget" has to be checked in the config, not assumed from the paper. This was one of four parity violations `parity_manifest.py` caught on its first run, all biasing toward HELIX.

### E4. Integrity audit — the three cut results

| result | reported | mechanism | how caught |
|---|---|---|---|
| circle_packing_rect | 2.3658 (= AlphaEvolve) | M1 memorised answer | matched published value to 6+ s.f.; literals in source |
| prism | 40.289 (53% above field) | M2 unchecked constraint | candidate contained prose reasoning about the checker |
| signal_processing | 0.7371 (above EvoX) | non-causal lookahead | filter read future samples |

Plus in B1: `b1_lru_graph_singlefile g5-s5` (M4+M5+M6 composed, 827,366× over seed) and `b1_ml_loop_singlefile g4-s4` (M6, `__len__ = 0`, 351,657×).

**Learned.** Every exploit appears as a discontinuous jump of 10³–10³⁰⁰×. Every genuine result appears as a gradient. That is the single most useful heuristic we have, and it needs no keyword.

### E5. Heilbronn triangle (B.9)

**What.** Three seeds. s0 0.0365297529, s1 0.0365298899, s2 0.0336298986 (one candidate flagged, excluded).

**Analysis.** s1 matches AlphaEvolve's 0.036529889880030156 to 12 decimal places — an exact tie, not a beat. Beats published AdaEvolve (0.036), EvoX (0.0339), GigaEvo (0.0364), Friedman (0.036) by 0.4–7.8%. Karim flagged the AdaEvolve margin (1.47%) as not significant; he was right that it is narrow. It is a real ordering on a deterministic constructive bound but not a headline.

**Learned.** An earlier version of `verify_all_claims.py` graded this against 0.036 (a rounded figure) and reported WIN. Against AlphaEvolve's actual 0.0365298899 it is a tie. Rounded comparators manufacture wins.

### E6. Circle packing n=26 (B.12)

**What.** Reached 2.635983085. AlphaEvolve's published 2.63586276 is beaten by 0.0047%.

**Then.** `tasks.tsv` records ShinkaEvolve at 2.635983283. We are 2 × 10⁻⁷ below the actual record — a tie to 7 significant figures.

**Integrity.** Matching a published value to 7 s.f. is the M1 signature. Checked: 0/7 flagged, zero high-precision literals, no reference to published values, gradual progression 0.96 → 2.58 → 2.62 → 2.63 → 2.636. Genuine convergence to the true optimum.

**Learned.** The evaluator has *no* `BENCHMARK` constant — the 2.63586 I'd been quoting came from the draft, not the benchmark. I nearly reported a win against a target I had carried over rather than read. Always locate the comparator in the benchmark's own files.

### E7. Third autocorrelation (B.3)

**What.** 0.9984230 normalized at 72/200 evaluations. 0.158% short of AlphaEvolve. Still improving when stopped for budget.

**Status.** Near-miss. Even if it crossed, AdaEvolve was not run on it, so it would be a beat of AlphaEvolve's number only.

### E8. Heilbronn convex (n=13)

**What.** s1 reached 0.9563 normalized (≈0.0296 raw) at 200/200. Field: AlphaEvolve 0.0309, human 0.0306, AdaEvolve 0.029, EvoX 0.0272, GEPA 0.027.

**Analysis.** Beats AdaEvolve, EvoX and GEPA's published numbers. Does not beat human or AlphaEvolve. Notable because AdaEvolve and EvoX both lose to the human baseline here — it was the only problem where crossing the top would have beaten the *entire* field rather than tying.

### E9. Unrun problems — cut

erdos_min_overlap (30% seed gap), sums_diffs_finite_sets (15%), uncertainty_ineq (15%). All had incomplete `requirements.txt` (missing tqdm / jax / optax), patched. Smoke-tested (0.867, 0.769, 0.868). Not pursued: user said "I don't want long shot, I want wins," and B.2's gap was 4.7% by comparison.

### E10. The confounded ablation — RETRACTED

**What.** Existing `b3_*_t1` and `b3_*_t5` directories on disk showed full=1.0, t1=0.4, t5=0.4 for b3_1 and b3_3. I recommended this as a turn-budget result.

**Then.** Checked the configs. The "full" arms ran `claude-opus-4-5-20251101` via `ANTHROPIC_API_KEY` against raw pytest; the t1 arms ran `sonnet` on Max plan via `ablation_guard`. Four variables moved at once. Unreportable.

**Learned.** I recommended a result before checking that its arms differed in one variable. The check took thirty seconds. Also: all five original B3 "full" runs — including the B3.1/3.2/3.4 GEPA wins in the old claims table — were Opus-via-API, not Max-plan Sonnet, and were never comparable to anything else.

### E11. Matched B3 turn sweep

**What.** All arms regenerated: sonnet, Max plan, `ablation_guard`, identical prompt, `max_turns ∈ {1,2,3,5,10,20}`, 5 tasks, 30 cells. Only the `max_turns` line differs between arms, verified by diff.

**Setup faults caught before spending quota.** (i) Staged dirs weren't git repos, so `ablation_guard` saw every file as untracked → scope violation → seed scored 0. Every candidate would have scored 0. (ii) With that fixed, seeds scored 0.40/0.25/0.20/0.40/0.40 — exactly the "GEPA per-file" numbers in the old claims table. GEPA had never moved from the seed.

**Result.** Table 1 in the draft. Threshold at T=3 for four tasks, T=5 for one. Flat T5→T20. Zero partial credit.

**The T=1 arm is degenerate, not weak.** `terminal_reason: max_turns`, 1,368 output tokens across a whole run, only `.gitignore` written. The agent spends its one turn on one tool call and is cut off. It is strictly *weaker* than AdaEvolve's operator (one call, whole program as text, no tools). T=2 — where the agent *can* read-then-edit — is the first fair data point, and it also fails. That is what makes the result meaningful.

### E12. GEPA on B3, matched

**What.** GEPA via the Max-plan callable, concatenated variant, `max_metric_calls = 20`.

**Result.** 0.40, 0.25, **1.00**, 0.40, 0.60. GEPA solves 1/5 (enum_migration), improves 1 (module_restructure), stuck at seed on 3.

**Learned.** The old "GEPA solves 0/5" was wrong. Also: my first score extraction returned `None` (`GEPAResult` has no `.best_score`); had to parse the log. Recorded conditions in the JSON so the number cannot be quoted without them.

### E13. Real-repository tasks — construction

**What.** Cloned tenacity, python-dotenv, packaging, structlog, toolz, humanize, boltons. Built `make_task.py`: rename a widely-used symbol in tests only; validate that (i) baseline is green, (ii) rename in tests breaks it, (iii) same rename in source restores it.

**Rejected by validation (7 of 10).** structlog BoundLogger and PrintLogger (23 traceback tests capture class names); packaging SpecifierSet (14 collection errors); tenacity AttemptManager and boltons OrderedMultiDict (tests never exercised them); toolz memoize and frequencies (suite didn't run — missing deps).

**Shipped.** tenacity RetryCallState (10 modules), tenacity stop_after_attempt (3), boltons cachedproperty (2). python-dotenv had a pre-existing failure; toolz had one; both would have needed tolerance logic. Setup faults: `--with .` fails because setuptools-scm needs git metadata the task copy drops → switched to `PYTHONPATH`.

**Learned.** Rejecting 70% of candidates was the right call. The validator's third check — "the reference fix must restore green" — is what makes every shipped task provably solvable, and it is what a reviewer would ask for first.

### E14. Real-repository turn sweep

**What.** T ∈ {20,3,2,1} first, then {10,5} to locate the two unresolved thresholds.

**Result.** Table 2. Eighteen cells, all 0.0 or 1.0. RetryCallState flips at T3; the other two flip at T5.

**Learned.** The task with the *most* coupling (10 modules, 100 edits) has the *lowest* threshold. Neither file count nor edit count predicts difficulty. Hypothesis (untested): stop_after_attempt and cachedproperty are public API names with `__all__` entries and doc references, so a correct fix requires judgment about what to rename, whereas RetryCallState is purely internal. We report the anomaly, not the hypothesis.

### E15. Integrity check on real-repo solutions — the two-threshold finding

**What.** Inspected every winning candidate's diff against its seed commit.

**Found.** RetryCallState: 10 files changed, 0 old-name references left, no test or protected file touched — a complete refactor. boltons: correct (the surviving `cachedproperty` is an independent duplicate class in `urlutils.py`). **stop_after_attempt at T5: class renamed, `__all__` still exports the old name, `from tenacity import *` raises AttributeError, all 184 tests pass anyway.** At T10 and T20 the same task is complete.

**Fix.** Added a completeness gate to all 16 evaluators (every `__all__` name must resolve; failing candidates capped at 0.99 with the reason in side-info). Re-scored every winner: 7/8 complete.

**Learned.** This is the paper's connecting result. The metric's threshold is lower than the specification's. At the exact budget where the metric flips, the operator produces the cheapest thing that flips it. My first diff check used `git diff HEAD` and showed nothing — HELIX commits the mutation, so the right comparison is against the seed commit. Wrong comparison looked like an exploit; right comparison showed a real refactor.

### E16. GEPA on real repositories

**What.** Concatenated variant, 13 files / 83,501 chars for tenacity.

**Result.** 0/3. Every task scored 0.000.

**Validation.** Fed HELIX's known-good RetryCallState solution through GEPA's own evaluator path → 1.0. Harness works.

**Learned.** A baseline scoring zero everywhere is exactly what a broken harness produces; the scipy and tqdm bugs both looked like that. The known-good probe is the only thing that distinguishes "baseline failed" from "harness failed," and it must be run before the number is reported.

### E17. Seeds at threshold cells

**What.** Two extra `rng_seed` values on the six arms bracketing transitions.

**Result.** Table 3. RetryCallState 3/3 both sides. stop_after_attempt T5: 1.0, 1.0, **0.0**. boltons cells skipped when quota ran out.

**Learned.** The transition is real but its location has variance. "T5 is above threshold" is wrong; "T5 is at threshold" is right. With n=1 we would have reported the former.

### E18. AdaEvolve on B.2 — run 1 destroyed, run 2 reproduced

**What.** Run 1 reached 0.9250655 at iteration 16. It wedged (host slept, wake deadline passed). I restarted it into the same directory and **overwrote the checkpoints**. The evidence was gone. Run 2, in a fresh directory with `CLAUDE_CLI_CONCURRENCY=1`, reached 0.9318 verified.

**Learned.** Never restart into an existing run directory. The claim survived only because run 2 independently reproduced it.

---

## Part II — Bugs that produced wrong numbers

| # | bug | wrong number it produced | how found |
|---|---|---|---|
| B1 | `check_integrity.py` read scores from a deprecated path; magnitude backstop guarded on having a score; printed "0/N flagged" with no scores resolved | "clean" on every run for weeks, including documented M6 exploit | noticed it cleared a known exploit |
| B2 | `verify_all_claims.py` bars set to AlphaEvolve's published value, not strongest known | 7/9 wins; real figure 3/9 | AdaEvolve and ShinkaEvolve data |
| B3 | B.12 comparator carried from draft, not read from benchmark | "beats AlphaEvolve" when actually tied ShinkaEvolve | grep found no `BENCHMARK` constant |
| B4 | Baseline harness discarded stderr on `is_error=true`; raised on first non-429 error | 3 of 13 iterations lost to blank "LLM error:" (~23%) | log inspection |
| B5 | Baseline harness restarted without `CLAUDE_CLI_CONCURRENCY=1` | 2,098 "Not logged in" failures; retry logic dressed them as transient | every flag combination worked in isolation → contention |
| B6 | AdaEvolve restarted into `run1` | destroyed the 0.9250655 checkpoint | noticed `checkpoint_20` now read iter 2 |
| B7 | Supervisor: liveness = process exists | guarded a wedged circle_packing for 4.5 h | zero worktree writes, zero agents |
| B8 | Supervisor: idle measured from stale worktree mtimes, no grace after restart | killed circle_packing twice in 5 min | log |
| B9 | Supervisor: `pgrep -f run_baseline_max` matched my own watcher script | "two AdaEvolve runs" false alarm | inspected pid args |
| B10 | Monitor exited on first empty sample during a restart gap | stopped recording usage overnight | log ended at 07:34 |
| B11 | `overnight.py` spend cap compared against all-time total ($348) | would have refused to start anything | noticed on launch |
| B12 | `overnight.py` skipped seeds because "has any state" ≠ "finished" | seeds never ran | morning check |
| B13 | Staged ablation dirs not git repos | `ablation_guard` scored seed 0 (scope violation) | smoke test before spending |
| B14 | Skydiscover baseline venv missing 13 packages HELIX had | baseline candidates using scipy/jax/torch would score 0 | `parity_manifest.py` |
| B15 | `parity_manifest.py` false positive on scikit-learn (import name sklearn) | reported missing package that was present | IMPORT_NAME map |
| B16 | Killed the user's Codex campaign twice | lost progress on two of their runs | user told me |
| B17 | `git diff HEAD` on a HELIX worktree | empty diff looked like the agent cheated | HELIX commits mutations; diff against seed |
| B18 | Grep for "Best C2" took last line (per-island) / mixed normalized and raw | reported 0.88, then 0.98, then 0.0 | extracted verified `c2=…, combined_score=…` pairs |
| B19 | GEPA `.best_score` attribute doesn't exist | `best=None` on completed runs | parsed log |
| B20 | Existing B3 "full" runs were Opus+API, ablation arms were Sonnet+Max | confounded four variables | config diff |

**The pattern.** Twenty bugs, and in fourteen of them the *checking tool itself* was wrong rather than the thing being checked. A gate that never fires is worse than no gate, because it manufactures confidence. Every gate we now have was negative-tested.

---

## Part III — Dead ends and why

- **GSO benchmark.** Costed at 2,040 agent sessions on Max plan. Reversed.
- **Frontier-CS.** User tried it, very expensive. Not proposed again.
- **AlgoTune.** 154 tasks; identified as a Phase-2 target; not pursued in this window.
- **ARC-AGI / AIME / Can't Be Late (Track A).** Can't Be Late's 82.33% is an inverted metric (dollar cost / 200); the evaluator ignores its argument. Not usable as reported.
- **Error-bar seeds on B.2.** Staged and normalised (s1/s2 had carried a heilbronn-specific prompt paragraph; regenerated to differ only in `rng_seed`). Never completed. Deprioritised once B.2 became a verified loss — an error bar on a losing claim is not worth budget.
- **circle_packing to 200 evals.** Converged at the ShinkaEvolve optimum by eval 60; nine hours and three restarts produced nothing. Dropped.
- **Cross-backbone heilbronn arms** (gpt-5.6-sol, gemini-3-pro). Exist on disk, pass API keys, excluded from the Max-plan table by the parity gate. Would be a separate "backbone sensitivity" table if wanted.

---

## Part IV — Future work, by value

### Before submission (18 days), in order

1. **Write.** No `.tex` exists. `ICLR_DRAFT.md` is complete prose for every section; it needs LaTeX, figures, and Karim's voice. This is the binding constraint. Nothing below matters if this doesn't happen.
2. **boltons seed cells** (T3 s1/s2, T5 s1/s2). ~20 min. Makes every real-repo transition n=3.
3. **Re-run stop_after_attempt T5/T10/T20 under the completeness gate.** ~30 min. Removes the "gate added after the fact" limitation.
4. **AdaEvolve on the three real repos.** ~1 h. Second baseline; turns "GEPA 0/3" into "the single-call family 0/3."
5. **Figure: the threshold.** One plot, three panels (authored / real / seeds), score vs turns, step function visible.
6. **Stop.** Every additional experiment is an hour not spent on the manuscript.

### If time permits

- **A fourth real-repository task** from a validated candidate with a different refactor type (signature change rather than rename), to address the "one transformation type" limitation.
- **T=4 arms** on the two T5-threshold tasks, to pin the transition.
- **Backbone sensitivity table** from the existing gpt-5.6-sol / gemini arms, clearly separated from the Max-plan table.

### After submission

- **Why is the threshold where it is?** Instrument the agent's tool calls per turn; test the public-API hypothesis directly.
- **Does the threshold move with backbone?** Same sweep on a weaker model.
- **Integrity checker as a first-class component.** Per-candidate, magnitude-based, fail-closed, with the known-good probe built in.
- **HELIX on AlgoTune** (154 CPU-speedup tasks, top result 2.05×) — the natural Phase-2 public benchmark, and one where "work moved outside the timer" (M4) is the dominant risk.

---

## Part V — Learnings

**About the science.**
- The operator's turn budget is a threshold, not a dial. This held on 8 tasks across two scales and three seeds where tested.
- The threshold is task-specific and is not predicted by coupling breadth.
- Test pass rate has a lower threshold than correctness. The operator finds the gap.
- Single-call optimisers sit below the threshold by construction; on real code they score zero.
- HELIX does not beat the field on the AlphaEvolve problems. It ties twice and loses once. AdaEvolve's multiscale continuation is a better optimiser than anything HELIX found.

**About measurement.**
- Grade against the strongest known result, located in the benchmark's own files. Every "win" that evaporated did so because the comparator was convenient rather than correct.
- A zero-scoring baseline is a harness bug until a known-good solution scores 1.0 through the same path.
- A gate that cannot fail is not a gate. Negative-test every check.
- "Verified clean" and "could not verify" must be different outputs.
- Exploits are discontinuities; results are gradients.
- Restart into a fresh directory, always.

**About process.**
- Check that an ablation's arms differ in one variable *before* recommending it, not after.
- A liveness check that tests "process exists" guards corpses.
- The user's other work on the machine is invisible until it isn't. Filter every process match to your own naming scheme.
- Treat every number you produce as provisional until it has been through `verify_all_claims.py`. Fourteen of twenty bugs were in the checking tools.
