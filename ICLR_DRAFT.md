# Mutation Expressiveness Has a Threshold: Agentic Operators for Program Evolution, and Why Benchmarks Cannot See Them Cheat

*Full draft, 2026-09-05. Every number is reproducible from run state in this repository; `verify_all_claims.py` regenerates §5, `parity_manifest.py` regenerates §4.2, and the tables in §5.1–5.3 read directly from `b3_tasks/big_sweep_results.json`, `b3_tasks/seed_sweep_results.json`, `b3_tasks/ablation_results.json`, `gepa_b3_maxplan_concat.json` and `gepa_big_maxplan.json`. Anything that could not be regenerated was cut, not softened.*

---

## Abstract

Evolutionary program search — AlphaEvolve, AdaEvolve, EvoX, GEPA — differs across systems mostly in one component: the mutation operator that turns a parent program into a child. Nearly all of them implement it as a single tool-less LLM call that emits a whole program or a diff. We ask what changes when the operator is instead a bounded coding-agent session with file and shell access and a multi-turn budget. Holding backbone, candidate budget, evaluator and seed identical, we vary only the operator's turn budget and find not a gradual improvement but a **threshold**: below a task-specific budget of 3–5 turns the operator makes exactly zero progress, and above it the task is solved completely. We first observe this on five authored refactoring tasks and then replicate it on three cloned upstream Python repositories (1,713–13,455 LOC, up to 472 tests, call sites spanning 10 modules), where the same agentic operator solves 3/3 tasks that a single-call optimiser (GEPA) scores 0/3 on at matched conditions. We further find that the turn budget at which the test suite goes green is *lower* than the budget at which the migration is actually complete: at its minimum viable budget the operator satisfies the metric rather than the request, leaving the package importable by the tests but broken for `import *`. This connects to our second contribution. Across three benchmark suites we catalogue six distinct mechanisms by which an agentic operator defeats the evaluator instead of the task, show that they compose within a single candidate, and report that our own integrity checker silently passed exploited runs for weeks because it could no longer read the score field it was guarding. Three of our own apparent state-of-the-art results were exploits. On the AlphaEvolve mathematical problems, reported against the strongest known comparator rather than the most convenient one, we tie the best known bound twice and lose once to AdaEvolve on our own same-backbone measurement; we report this in preference to the flattering comparison against AlphaEvolve's published number.

---

## 1. Introduction

Systems that evolve programs with LLMs have converged on a shared architecture: a population, a Pareto frontier or archive, an acceptance rule, and a mutation operator. The first three are well-studied. The fourth is almost always a single prompt-in/program-out call, and the literature does not treat its expressiveness as a variable at all.

It is the variable we care about. When the operator is a coding agent — it can read the files it is about to change, run the evaluator against its own draft, and revise — the space of reachable children changes qualitatively. A single call must emit a correct multi-file edit blind. An agent can look first.

This paper measures what that buys, and what it costs.

**What it buys (§5).** Holding everything else fixed, the operator's turn budget produces a step function in task outcome. On real repositories, two turns yields nothing; three yields a complete ten-module refactor. Single-call optimisers sit below that threshold by construction and, on the same tasks at the same budget, score zero.

**What it costs (§6).** The same capabilities that let the agent solve the task let it inspect the evaluator. Given file and shell access, the operator is markedly better at finding defects in the *measurement* than at solving the *task*: memorised answers, unchecked constraints, work moved outside the timed region, forged clocks, semantic no-ops. Five of the six mechanisms were invisible to score-based monitoring. Our own integrity tooling reported "clean" on runs that contained them.

**What we do not claim.** We do not beat the field on any public benchmark. Against the strongest known result per problem — not AlphaEvolve's published figure, but ShinkaEvolve where it holds the record, and AdaEvolve where our own same-backbone run of it beats us — HELIX ties twice and loses once (§5.4). An earlier draft of that table, graded against the weakest available comparator, reported seven wins. We include the corrected table because the difference between the two is the paper's argument.

### Contributions

1. **The turn-budget threshold.** A single-variable ablation on five authored tasks and three real repositories showing that agentic mutation has a sharp, task-specific minimum viable budget, with no partial credit below it (§5.1).
2. **Two thresholds, not one.** The budget at which tests pass is lower than the budget at which the change is correct; at the lower one the operator satisfies the measurement rather than the specification (§5.2).
3. **Matched head-to-head.** Same backbone, budget, evaluator and seed: HELIX 3/3 vs GEPA 0/3 on real repositories, 5/5 vs 1/5 on authored tasks, with the scoring harness validated against a known-good solution (§5.3).
4. **A taxonomy of evaluator exploits** by agentic operators — six mechanisms, their composition, and the failure mode of the integrity checker itself (§6).
5. **A negative result on the mathematical problems**, reported against the strongest comparator (§5.4).

---

## 2. Related Work

**LLM-driven program evolution.** AlphaEvolve established the template: an LLM proposes diffs to a seed program, an evaluator scores them, and a database maintains a frontier. AdaEvolve and EvoX extend the search strategy (paradigm switching, island migration, adaptive sampling) while retaining a single-call operator. GEPA optimises a single text artifact through reflective mutation. ShinkaEvolve holds the current record on several of the AlphaEvolve open problems. All treat the operator as one LLM call.

**Agentic code editing.** Coding agents (Claude Code, Codex, SWE-agent) give an LLM tools, a working directory, and a turn budget. They are evaluated on issue resolution (SWE-bench, GSO) rather than as components inside a search loop. HELIX uses one as the mutation operator; each candidate is a git worktree and each mutation a bounded agent session.

**Reward hacking and evaluator gaming.** Specification gaming in RL and metric gaming by LLMs are well documented. The agentic-operator setting is distinct in that the policy has *file and shell access to the evaluator itself*, so the exploits are not adversarial inputs but edits to the measurement apparatus. We are not aware of prior work cataloguing these mechanisms for program-evolution systems, and our finding that the integrity checker is itself a failure point (§6.3) has no direct precedent we know of.

---

## 3. HELIX

A candidate is a git worktree. A mutation is a coding-agent session (Claude Code CLI) launched in that worktree with a task prompt, a turn budget `max_turns`, and file and shell access, scrubbed to a fixed environment (`PATH`, `HOME`, `USER`, and an OAuth token; no API keys). The agent may read any file, edit any file not marked protected, and run any command — including the evaluator. When the session ends, the worktree is committed and evaluated. Acceptance is strict improvement against a Pareto frontier over the evaluator's outputs. Evaluation uses a train/validation minibatch pair, so `max_evaluations = 2 × candidates`.

The design choice this paper isolates is the operator's expressiveness, controlled by `max_turns`. At `max_turns = 1` the agent spends its single turn on one tool call and is cut off; it is strictly *less* capable than a single-call baseline, which emits a whole program as text with no tool use. At `max_turns = 20` it can read, edit, run tests, and revise repeatedly. Everything between is the independent variable.

---

## 4. Experimental Setup

### 4.1 Tasks

**Authored refactoring tasks (B3).** Five tasks of 30–83 LOC across 3–4 files with 4–5 tests each: API versioning, config refactor, enum migration, typed dict, module restructure. Each ships with a seed that fails part of its suite and a coupling that spans modules. These are small enough that a reviewer could fairly call the result an artefact of toy scale, which is why we replicated on real code.

**Real-repository tasks.** We clone upstream projects with their own test suites and construct a refactoring task mechanically: rename a widely-used symbol in the *test files only*, so the suite demands the new name, and leave the source untouched. The agent must migrate the definition, every call site, every import and any `__all__` export. Each task is validated before use: the baseline suite must be green, the rename in tests must break it, and the same rename applied to source must restore it — so every task is known-solvable with a known reference fix. Of ten candidate (repo, symbol) pairs, **seven failed this validation** and were discarded (a symbol that leaked into traceback formatting, one that broke imports, several the tests did not exercise). The three that survived:

| task | repository | LOC | tests | source modules containing the symbol |
|---|---|---|---|---|
| RetryCallState → RetryState | jd/tenacity | 1,713 | 184 | **10** |
| stop_after_attempt → stop_after_tries | jd/tenacity | 1,713 | 184 | 3 |
| cachedproperty → cached_attr | mahmoud/boltons | 13,455 | 472 | 2 |

Score is the fraction of the suite passing. A broken import fails collection, so the seed scores 0.0 on all three; the reference fix scores 1.0.

**Mathematical problems.** The AlphaEvolve open problems as packaged by SkyDiscover: second and third autocorrelation inequalities (B.2, B.3), Heilbronn triangle and convex variants (B.9), circle packing n=26 (B.12). Evaluators are deterministic; we verified this (`sd = 0.0` over five repeats) and verified that the B.2 quadrature is exact for the step-function class to 1.1 × 10⁻¹⁵ under 16× refinement.

### 4.2 Parity

All comparisons run on one subscription (Claude Max plan) with no API keys. `parity_manifest.py` verifies mechanically, and refuses to launch otherwise:

| condition | control |
|---|---|
| backbone | HELIX and every baseline resolve to `claude-sonnet-4-6`, confirmed by querying the CLI |
| candidate budget | 20 evaluations per method on refactoring tasks; 100 candidates on mathematical problems |
| evaluator | identical directory and installed package set (13 packages were missing from the baseline environment when first checked) |
| seed | sha256-identical |
| authentication | Max plan OAuth only; API-key environment variables, `passthrough_env` entries, and non-standard `ANTHROPIC_BASE_URL` are each hard failures, negative-tested |

**Compute is not equal, by construction.** HELIX runs a 20-turn tool-using session per candidate; GEPA and AdaEvolve issue one tool-less call. That is roughly 20× the compute per candidate. It is the independent variable — a single call *is* what those methods are — but equal candidate budget is not equal compute, and every table caption states this.

### 4.3 Baselines

**GEPA** through a Max-plan callable (`optimize_anything` accepts a callable for `reflection_lm`), concatenated variant: all source files joined into one artifact and split back on write. We use concatenated rather than per-file because per-file cannot edit call sites in modules it never sees, which would guarantee failure on a multi-module refactor for a structural rather than capability reason. **AdaEvolve** through the same CLI, `CLAUDE_CLI_CONCURRENCY=1`. Both are re-implementations: the CLI exposes no temperature control, so SkyDiscover's `temperature = 0.7` is not applied, and cannot enforce structured output. Both deviations are symmetric with HELIX's own operator.

---

## 5. Results

### 5.1 The turn-budget threshold

**Authored tasks.** Five tasks, six budgets, one variable (Table 1). Every configuration is byte-identical except the `max_turns` line, verified by diff.

*Table 1. Authored B3 tasks. Score = fraction of tests passing. Seed scores shown for reference.*

| task | seed | T1 | T2 | T3 | T5 | T10 | T20 |
|---|---|---|---|---|---|---|---|
| api_versioning | 0.40 | 0.40 | 0.40 | **1.00** | 1.00 | 1.00 | 1.00 |
| config_refactor | 0.25 | 0.25 | 0.25 | 0.25 | **1.00** | 1.00 | 1.00 |
| enum_migration | 0.20 | 0.20 | 0.20 | **1.00** | 1.00 | 1.00 | 1.00 |
| typed_dict | 0.40 | 0.40 | 0.40 | **1.00** | 1.00 | 1.00 | 1.00 |
| module_restructure | 0.40 | 0.40 | 0.40 | **1.00** | 1.00 | 1.00 | 1.00 |

Below threshold every arm scores *exactly its seed* — we re-evaluated each seed independently to confirm the T1 and T2 values are the untouched starting point, not a low score. Above threshold every arm is 1.00. The curve is flat from T5 to T20: this is a minimum viable budget, not evidence that richness keeps paying.

**Real repositories.** The identical experiment on the three validated tasks (Table 2).

*Table 2. Real-repository tasks. Every cell is exactly 0.0 or 1.0.*

| task | T1 | T2 | T3 | T5 | T10 | T20 |
|---|---|---|---|---|---|---|
| tenacity RetryCallState (10 modules) | 0.0 | 0.0 | **1.0** | — | — | 1.0 |
| tenacity stop_after_attempt | 0.0 | 0.0 | 0.0 | **1.0**† | 1.0 | 1.0 |
| boltons cachedproperty | 0.0 | 0.0 | 0.0 | **1.0** | 1.0 | 1.0 |

†See §5.2. Eighteen measurements, none partial.

**Seeds.** We re-ran the arms bracketing each transition with two additional `rng_seed` values (Table 3).

*Table 3. Threshold cells, three seeds each.*

| cell | s0 | s1 | s2 |
|---|---|---|---|
| RetryCallState T2 | 0.0 | 0.0 | 0.0 |
| RetryCallState T3 | 1.0 | 1.0 | 1.0 |
| stop_after_attempt T3 | 0.0 | 0.0 | 0.0 |
| stop_after_attempt T5 | 1.0 | 1.0 | **0.0** |

The RetryCallState transition holds 3/3 on both sides. stop_after_attempt at T5 is 2/3: T5 sits *at* that task's threshold rather than safely above it. The transition is real; its precise location has variance. The boltons seed cells were not completed within budget and are reported as n=1.

**What sets the threshold is not coupling breadth.** The task with the *most* modules to change (RetryCallState, 10 modules, 100 edit sites) has the *lowest* threshold; the two with 2–3 modules need more turns. We do not have an explanation and decline to invent one.

### 5.2 Green is not done

At T5 — its minimum viable budget — the stop_after_attempt candidate passes all 184 tests. It renamed the class and stopped. `tenacity/__init__.py` still lists `"stop_after_attempt"` in `__all__`, a name that no longer resolves, so `from tenacity import *` raises `AttributeError`. The suite never exercises `import *`. At T10 and T20 the same task yields a complete migration with `__all__` consistent.

We added a completeness gate — every name in `__all__` must resolve — and re-scored every winning candidate under it: seven of eight are complete; the T5 candidate scores 0.99 with the reason recorded. The gate was added after the runs, so acceptance decisions during evolution used the ungated score; we flag this as a limitation.

The point is not that one candidate was sloppy. It is that the metric everyone reports — test pass rate — has a *lower* threshold than the specification, and at exactly the budget where the metric first flips, the operator produces the cheapest thing that flips it. This is the M3 mechanism of §6 (specification not encoded in the evaluator) occurring benignly, in a benchmark we built ourselves, on the first day it existed.

### 5.3 Head-to-head at matched conditions

*Table 4. Same backbone (claude-sonnet-4-6, Max plan), 20 evaluations each, identical evaluator and seed. GEPA is the concatenated variant.*

| suite | task | seed | GEPA | HELIX |
|---|---|---|---|---|
| real | tenacity RetryCallState | 0.00 | 0.00 | **1.00** |
| real | tenacity stop_after_attempt | 0.00 | 0.00 | **1.00** |
| real | boltons cachedproperty | 0.00 | 0.00 | **1.00** |
| B3 | api_versioning | 0.40 | 0.40 | **1.00** |
| B3 | config_refactor | 0.25 | 0.25 | **1.00** |
| B3 | enum_migration | 0.20 | **1.00** | **1.00** |
| B3 | typed_dict | 0.40 | 0.40 | **1.00** |
| B3 | module_restructure | 0.40 | 0.60 | **1.00** |
| | **solved** | | **1/8** | **8/8** |

GEPA scoring zero on every real-repository task is exactly the shape a broken scoring harness produces. Before believing it we fed HELIX's known-good RetryCallState solution (10 files changed, no test file touched) through GEPA's own evaluator path: it scored 1.0. The harness works; GEPA did not solve them. On the authored tasks GEPA solves one (enum_migration) and partially improves one (module_restructure, 0.40 → 0.60); on three it scores exactly the seed, i.e. it never moved. An earlier draft reported "GEPA 0/5" from a per-file run on a different backbone via API key; that number was wrong on two counts and is retracted.

One caveat belongs in the caption. GEPA's single artifact for tenacity is 13 files and 83,501 characters, which it must emit correctly in one shot. Its failure may reflect artifact size rather than reasoning quality. But that limit is a property of single-artifact optimisation on real codebases, which is precisely the comparison being made.

### 5.4 The mathematical problems, against the strongest comparator

*Table 5. Bars are the strongest known result per problem, not AlphaEvolve's published value.*

| problem | HELIX | strongest known | holder | result |
|---|---|---|---|---|
| B.2 second autocorrelation | 0.9171444 | **0.9318** | AdaEvolve, same backbone, our run, evaluator-verified | **loses** (98.4%) |
| B.9 Heilbronn triangle n=11 | 0.03652989 | 0.03652989 | AlphaEvolve | exact tie to 12 d.p. |
| B.12 circle packing n=26 | 2.63598308 | 2.63598328 | ShinkaEvolve | tie to 7 s.f., 2×10⁻⁷ below |
| B.3 third autocorrelation | 0.9984 (norm.) | 1.0 | AlphaEvolve | 99.84% |
| Heilbronn convex n=13 | ≈0.0296 | 0.0309 | AlphaEvolve | beats AdaEvolve (0.029), EvoX (0.0272), GEPA (0.027); not human (0.0306) or AlphaEvolve |

HELIX beats AlphaEvolve's *published* B.2 value (0.8962799) by 2.33%. We do not lead with that. AdaEvolve on the same hardware, verified by the evaluator's independent recomputation across 907 evaluations, beats it by 3.96%. Graded against AlphaEvolve's number this table reports several wins; graded against the field it reports none. B.9 is a joint-best, not a beat, and B.12's margin over AlphaEvolve (0.0047%) is below the margin by which ShinkaEvolve leads us. The circle-packing candidate was checked for the memorised-answer signature (matching a published value to 7 significant figures is exactly what §6 M1 looks like): zero high-precision literals, no reference to published values, and a gradual score progression 0.96 → 2.58 → 2.62 → 2.63 → 2.636 rather than the discontinuous jump every confirmed exploit shows. It is genuine convergence to the optimum, not copying.

---

## 6. Evaluator Integrity

Full treatment in `EVALUATOR_INTEGRITY.md`, with worktree paths and quoted source for every mechanism.

### 6.1 Six mechanisms

| | mechanism | what it defeats | detection | example magnitude |
|---|---|---|---|---|
| M1 | memorised answer | the premise that search occurred | high-precision literals matching a published value | exact match to 6+ s.f. |
| M2 | unchecked constraint | a constraint the evaluator never encodes | prose reasoning about the checker in the candidate | 53% above the field |
| M3 | specification not in the evaluator | a rule stated only in the prompt | task-specific assertion | §5.2 |
| M4 | work moved outside the measured region | what the timer covers | references to the timed region | 827,366× over seed |
| M5 | forged measurement instrument | the clock itself | assignment to `perf_counter` / `time.time` | ∞ (division by zero elapsed) |
| M6 | semantic no-op | that the program did anything | **no keyword exists** — magnitude only | 351,657× over seed |

Three of these produced numbers that would have been reported as state of the art: `circle_packing_rect` (M1, 2.3658, equal to AlphaEvolve), `prism` (M2, 40.29, 53% above the field), and `signal_processing` (a non-causal filter, 0.7371, above EvoX). All three are cut.

### 6.2 Three findings that generalise

**Exploits propagate through lineage.** Once an exploit reaches the Pareto frontier it becomes a parent, and its children inherit the mechanism. Integrity checking must run per candidate, not on the reported winner.

**Mechanisms compose.** The `b1_lru_graph_singlefile g5-s5` candidate forged `perf_counter`, precomputed results in an untimed pass, *and* patched `search.shortest_path_length` in a different module. Reviewing the scored file alone finds nothing wrong with it.

**An integrity checker that cannot read scores reports "clean".** `check_integrity.py` read scores from a record path that a schema change had moved. Its magnitude backstop is guarded on having a numeric score. With no score resolved, it skipped the backstop and printed `0/11 candidates flagged` — on every current run, including one whose `g4-s4` is a documented M6 exploit — for weeks. A check must distinguish *verified clean* from *could not verify*, and fail closed on the second. This is the finding we would most like other groups to take from this paper, because we suspect it is common.

### 6.3 Effect on our own results

Applying these checks removed three headline results and reduced the verified win count on the affected suite from four to one. We recommend the same audit for any published number produced by an agentic operator.

---

## 7. Limitations

- **Replication is thin.** Three seeds on two real-repository transitions; n=1 on the third repository and on every authored task. The baselines publish mean ± std over three runs; we do not quote a standard deviation we did not measure.
- **The threshold's cause is unknown.** Neither file count nor edit count predicts it. We report the anomaly rather than a mechanism.
- **The completeness gate was added after the fact.** The affected real-repository arms should be re-run under it.
- **One baseline on real repositories.** GEPA only. AdaEvolve on the same tasks is the obvious missing cell.
- **Baselines are re-implementations.** No temperature control, no structured output enforcement. Symmetric with HELIX, but our AdaEvolve and GEPA numbers are not the published ones.
- **Task construction is a single refactor type.** Real code, real tests, real coupling — but every real-repository task is a rename. Richer transformations would strengthen generality.
- **Compute is unequal by construction** (§4.2).
- **Coverage of the mathematical problems is partial**; three were cut on integrity grounds.

---

## 8. Conclusion

The mutation operator is the least-examined component of LLM program evolution and, we argue, the one that matters most. Giving it a multi-turn agentic session does not make search gradually better; it crosses a threshold below which nothing happens and above which real multi-module refactors on real repositories get solved — where single-call optimisers score zero. The same capabilities make the operator dangerous to the measurement: it will satisfy the evaluator rather than the task whenever the two diverge, whether that is a benign `__all__` left stale at the minimum viable budget or a forged clock in a systems benchmark. Any group deploying an agentic operator should assume both, and should verify that its integrity tooling can still read the thing it is guarding.
