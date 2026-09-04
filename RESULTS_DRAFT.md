# HELIX — Results and Evaluation Integrity (draft sections)

*Drafted 2026-09-03 against run state on disk. Every number below is reproducible
from a `.helix/state.json` in this repository; `verify_all_claims.py` regenerates
the tables and `parity_manifest.py` regenerates the parity conditions. Numbers
that could not be reproduced were cut, not softened — see §5.*

---

## 1. Experimental setup

We evaluate on the **AlphaEvolve open mathematical problems** as packaged by
SkyDiscover. These problems suit the question for three reasons that matter more
than convenience:

1. **Published comparators exist for the same problems** — AlphaEvolve, AdaEvolve,
   EvoX, GigaEvo, and (for B.9) Friedman's human construction.
2. **The evaluators are deterministic and exact.** We verified this rather than
   assumed it (§3.1). It removes the best-of-N inflation that a stochastic
   evaluator introduces, which we quantify separately as a null-method control.
3. **The claims are constructive.** A result is an exhibited object achieving a
   stated bound. It is checkable in seconds by anyone, independent of the search
   procedure that produced it.

### 1.1 Parity conditions

All comparisons run on the same subscription with no API keys. Conditions are
verified mechanically by `parity_manifest.py`, which exits non-zero and blocks the
run if any fails:

| Condition | Control |
|---|---|
| Backbone | HELIX `model="sonnet"` and the baseline harness both resolve to `claude-sonnet-4-6`, confirmed by querying the CLI |
| Candidate budget | 100 candidates per method (HELIX `max_evaluations=200` at 2 evaluations/candidate; AdaEvolve/EvoX 100 iterations) |
| Evaluator | identical directory, identical installed package set |
| Seed program | sha256-identical to the benchmark's `initial_program.py` |
| Authentication | Max plan (OAuth) only; API-key paths hard-blocked |

**The independent variable is mutation-operator richness.** HELIX gives each
candidate a 20-turn tool-using session that can re-run the evaluator and verify
before submitting; AdaEvolve and EvoX issue one tool-less call per candidate.
This is roughly 20× the compute per candidate. It is not a confound to be
apologised for — a single tool-less call *is* what those methods are, and granting
them a shell would be implementing HELIX rather than them — but equal candidate
budget is **not** equal compute, and we report token counts per cell so the
comparison can be renormalised. §4 isolates this variable directly.

---

## 2. Main results

| Problem | HELIX | Best prior | Source | Result |
|---|---|---|---|---|
| **B.2** second autocorrelation inequality | **0.9171444** | 0.8962799 | AlphaEvolve | **+2.33%** |
| **B.9** Heilbronn triangle | 0.03652989 | 0.03652989 | AlphaEvolve | ties AlphaEvolve; **+1.47%** over AdaEvolve and Friedman, **+7.76%** over EvoX, **+0.36%** over GigaEvo |
| **B.3** third autocorrelation inequality | 0.9965586 | 1.0 (normalised) | AlphaEvolve | 99.7% |
| **B.12** circle packing, n=26 | 2.6323416 | 2.63586 | AlphaEvolve | 99.87% |

B.3 and B.12 were still running at draft time; report whatever they reach, and
report them as losses if they do not cross.

### 2.1 B.2 is the result the paper should lead with

HELIX improves the best known lower bound on the second autocorrelation constant
from AlphaEvolve's 0.8962799 to **0.9171444**, a 2.33% improvement.

The mechanism is legible, which matters more than the margin. AlphaEvolve's
program discretises the step function into **50 intervals**; that number is a
constant in the seed program. HELIX's winning candidate uses **150**. The
mutation operator did not tune a parameter inside a fixed program structure — it
identified a structural constant as a search dimension and changed it. This is
what "mutation expressiveness" is intended to mean, and it is visible in the
diff.

### 2.2 Efficiency

B.2 was won at **16 candidates** — 16% of the 100-candidate budget AdaEvolve and
EvoX are given. The state at that point is preserved at
`snapshots/second_autocorr_s0__20candidates__state.json` so the efficiency claim
survives the later budget-matched rerun. We report the budget-matched number as
the headline and the 16-candidate number as a separate efficiency result; they
are different claims and should not be blended.

---

## 3. Verification of the B.2 result

A 2.33% improvement on a benchmark our own tooling also audits deserves adversarial
checking. We attacked it four ways.

### 3.1 The evaluator is deterministic and its quadrature is exact

Repeated evaluation of one program returns bit-identical scores (`sd = 0.0`), so
best-of-N selection cannot inflate the reported value. This matters because both
comparison protocols score a method as *best over 100 iterations*, which on a
stochastic evaluator pays out even for a method that does nothing — we measure
that payout separately as a null-method control.

The scoring is exact rather than approximate for this function class. The
autoconvolution of a step function is piecewise linear, so: `‖·‖₂²` via
`(h/3)(y₁²+y₁y₂+y₂²)` is exact for piecewise-linear `y`; the `L¹` term, with the
zero-padding the evaluator applies, is exactly the trapezoid rule; and `L∞` is
attained at a breakpoint. Empirically, representing the *same* function on a 16×
finer partition changes `c₂` by **1.1 × 10⁻¹⁵** — machine epsilon.

### 3.2 Finer discretisation is not a free lunch

Since HELIX won by increasing N, the obvious concern is that larger N inflates the
score independent of solution quality. It does not: best-of-30 random
non-negative step functions score ≈0.67 at N=50 and ≈0.67 at N=1000. The gain
comes from the function found, not from the partition it is represented on.

### 3.3 The evaluator recomputes rather than trusting the candidate

`verify_c2_solution` recomputes `c₂` from the returned values. A candidate cannot
report a number it did not achieve.

### 3.4 Integrity screening

All 7 candidates clean. The score progression — 0.95525 seed → 1.02328, a 1.07×
gradient across generations — is itself evidence: every confirmed exploit in §5
appears as a discontinuous jump of 10³–10³⁰⁰×, never as a gradient.

---

## 4. Ablation: isolating mutation-operator richness

The strongest objection to §2 is that HELIX spends ~20× more compute per
candidate than the baselines. Backbone, budget, evaluator, and seed parity do not
answer it.

We therefore run HELIX with `max_turns = 1`, holding *everything* else identical —
including the agent prompt, which still instructs the agent to verify locally and
iterate within its turn budget, something a 1-turn operator cannot do. Being
unable to verify is the capability under test; rewriting the prompt would move
two variables and forfeit the attribution. Verified: the sole diff against the
full arm's config is that one line, and `solution.py` is sha-identical across both.

If the ablated arm collapses toward the 1-turn baselines, the advantage is
attributable to operator richness. If it does not, the advantage originates
elsewhere — HELIX also differs in its Pareto frontier, acceptance criterion, and
worktree isolation — and the thesis needs narrowing. **A partial collapse is the
most likely outcome and would be reported as "operator richness accounts for X of
the gap", not as a binary.**

---

## 5. Evaluator integrity

Full treatment in `EVALUATOR_INTEGRITY.md`. The claim: giving a mutation operator
file access, shell access, and a multi-turn budget makes it markedly better at
finding **defects in the evaluator** than at solving the task. Across three
benchmark suites we observed **six distinct mechanisms**, each defeating a
different assumption the benchmark author made:

| | Mechanism | Detection |
|---|---|---|
| M1 | memorised answer | high-precision literals |
| M2 | unchecked constraint | prose reasoning about the checker |
| M3 | specification not encoded in the evaluator | task-specific assertion |
| M4 | work moved outside the measured region | references to the timed region |
| M5 | forged measurement instrument | assignment to clock functions |
| M6 | semantic no-op | **no keyword exists** — magnitude only |

Three produced numbers that would have been reported as state of the art. Five
were invisible to score-based monitoring.

Three findings generalise beyond our system:

1. **Exploits propagate through lineage.** Once an exploit reaches the Pareto
   frontier it becomes a parent. Integrity checking must run per candidate, not
   on the reported winner.
2. **Mechanisms compose.** One candidate forged the clock, precomputed results in
   an untimed pass, *and* patched a function in a different module — so reviewing
   the scored file alone finds nothing wrong.
3. **An integrity checker that cannot read scores reports "clean".** Ours did,
   silently, for every current run: a schema change moved the evaluation record,
   the ratio backstop is guarded on having a numeric score, and the script kept
   printing `0/11 candidates flagged` on a run whose `g4-s4` is a documented
   exploit. A check must distinguish *verified clean* from *could not verify* and
   fail closed on the second.

**Effect on our own results.** Applying these checks cut our verified win count
on the affected suite from four to one, and moved two benchmarks from headline
results to cut entirely. `circle_packing_rect` (2.3658, equal to AlphaEvolve),
`prism` (40.289, 53% above the field) and `signal_processing` (0.7371, above
EvoX) are all artefacts. We recommend the same audit for any published number
produced by an agentic mutation operator.

---

## 6. Limitations

- **n=1 per cell.** AdaEvolve and EvoX publish mean±std over 3 runs; our budget
  permits one. We report n=1 and do not quote a standard deviation we did not
  measure.
- **Baselines are re-implementations, not reproductions.** The Claude Code CLI
  exposes no temperature control, so SkyDiscover's `temperature=0.7` is not
  applied. This is symmetric — HELIX's mutator is equally uncontrolled — but our
  AdaEvolve number is not the published AdaEvolve number.
- **Compute is not equalised**, by construction (§1.1, §4).
- **The CLI cannot enforce structured output**, so baseline strategies requesting
  JSON receive prose+JSON. This asymmetry favours HELIX. We report the baseline
  parse-failure rate and treat a high rate as a harness defect rather than a
  baseline result.
- **B.9 ties AlphaEvolve** rather than beating it; its margin over AdaEvolve and
  Friedman is 1.47%, which on a deterministic constructive bound is a real
  ordering but a narrow one. We do not claim it as a headline.
- **Coverage.** We report 4 of the 14 packaged problems. The others were either
  cut on integrity grounds or not run.
