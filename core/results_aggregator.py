"""Results aggregator for HELIX NeurIPS experiments.

Reads the results/<run_tag>/ directory produced by BatchRunner and computes:
    - Primary metrics:   mean/median/max score, solve rate
    - Efficiency metrics: tokens/mutation, evaluations-to-best, acceptance rate
    - Capability metrics: multi-file solve rate (Track B), per-task breakdown

Can compare two runs (e.g., GEPA vs. HELIX on the same problems) and output:
    - Terminal summary table
    - JSON for archiving
    - LaTeX table row ready to paste into the paper

Usage
-----
    python -m core.results_aggregator \
        --run results/gepa-alg-20260422 \
        --compare results/helix-alg-20260422 \
        --latex

Or import as a library:
    from core.results_aggregator import ResultsAggregator
    agg = ResultsAggregator("results/gepa-alg-20260422")
    agg.print_summary()
    agg.to_latex_row(label="GEPA O.A.")
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from dataclasses import dataclass
from typing import Optional


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass
class PaperMetrics:
    """All metrics the paper needs for one system × one benchmark."""
    label: str                      # e.g. "HELIX", "GEPA O.A."
    run_tag: str
    track: str
    optimizer: str
    n_problems: int
    n_ok: int
    n_error: int
    n_timeout: int

    # Primary task metrics
    score_mean: float
    score_median: float
    score_max: float
    score_std: float
    solve_rate: float               # fraction with score > 0

    # Efficiency metrics (from token logger)
    total_tokens: int
    tokens_per_mutation_avg: float  # total_tokens / total_accepted_mutations
    prompt_tokens_fraction: float   # prompt / total (how much is "reproduction")
    total_latency_s: float
    latency_per_call_avg_s: float

    # Acceptance / convergence
    acceptance_rate: float          # accepted mutations / total proposed
    evaluations_to_best_avg: float  # how many evals before best score (approx)

    # Per-problem scores for fine-grained analysis
    scores_by_problem: dict[str, float]


# --------------------------------------------------------------------------- #
# Aggregator
# --------------------------------------------------------------------------- #

class ResultsAggregator:
    def __init__(self, run_dir: str | pathlib.Path) -> None:
        self.run_dir = pathlib.Path(run_dir)
        if not self.run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {self.run_dir}")

        cfg_path = self.run_dir / "run_config.json"
        self.cfg: dict = {}
        if cfg_path.exists():
            self.cfg = json.loads(cfg_path.read_text())

        self._results = self._load_results()
        self._token_records = self._load_token_records()

    # --------------------------------------------------------------------- #
    # Loading
    # --------------------------------------------------------------------- #

    def _load_results(self) -> list[dict]:
        results = []
        for result_file in sorted(self.run_dir.rglob("result.json")):
            try:
                results.append(json.loads(result_file.read_text()))
            except Exception:
                pass
        return results

    def _load_token_records(self) -> list[dict]:
        records = []
        for tok_file in sorted(self.run_dir.rglob("tokens.jsonl")):
            try:
                for line in tok_file.read_text().splitlines():
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            except Exception:
                pass
        return records

    # --------------------------------------------------------------------- #
    # Metric computation
    # --------------------------------------------------------------------- #

    def compute(self, label: str = "") -> PaperMetrics:
        ok = [r for r in self._results if r.get("status") == "ok"]
        err = [r for r in self._results if r.get("status") == "error"]
        timeout = [r for r in self._results if r.get("status") == "timeout"]

        scores = [r.get("best_score", 0.0) for r in ok]
        scores_by_problem = {
            str(r.get("problem_id", "?")): r.get("best_score", 0.0)
            for r in ok
        }

        # Token stats from JSONL records
        total_prompt = sum(r.get("prompt_tokens", 0) for r in self._token_records)
        total_completion = sum(r.get("completion_tokens", 0) for r in self._token_records)
        total_tokens = sum(r.get("total_tokens", 0) for r in self._token_records)
        total_latency = sum(r.get("latency_s", 0.0) for r in self._token_records)
        n_calls = len(self._token_records)

        # Tokens per mutation: use result-level token summaries when available
        tok_per_mut_values = []
        for r in ok:
            ts = r.get("token_summary", {})
            n_calls_r = ts.get("total_calls", 0)
            tok_r = ts.get("total_tokens", 0)
            if n_calls_r > 0:
                tok_per_mut_values.append(tok_r / n_calls_r)

        # Acceptance rate: approximated from HELIX logs if available,
        # otherwise use 1.0 for GEPA (every proposal is counted as accepted)
        acceptance_rate = self._estimate_acceptance_rate()

        # Evaluations to best: approximate from GEPA's log structure
        evals_to_best = self._estimate_evals_to_best(ok)

        return PaperMetrics(
            label=label or self.cfg.get("optimizer", "unknown").upper(),
            run_tag=self.run_dir.name,
            track=self.cfg.get("track", "unknown"),
            optimizer=self.cfg.get("optimizer", "unknown"),
            n_problems=len(self._results),
            n_ok=len(ok),
            n_error=len(err),
            n_timeout=len(timeout),
            score_mean=statistics.mean(scores) if scores else 0.0,
            score_median=statistics.median(scores) if scores else 0.0,
            score_max=max(scores) if scores else 0.0,
            score_std=statistics.stdev(scores) if len(scores) > 1 else 0.0,
            solve_rate=sum(1 for s in scores if s > 0) / len(scores) if scores else 0.0,
            total_tokens=total_tokens,
            tokens_per_mutation_avg=statistics.mean(tok_per_mut_values) if tok_per_mut_values else 0.0,
            prompt_tokens_fraction=total_prompt / total_tokens if total_tokens else 0.0,
            total_latency_s=total_latency,
            latency_per_call_avg_s=total_latency / n_calls if n_calls else 0.0,
            acceptance_rate=acceptance_rate,
            evaluations_to_best_avg=evals_to_best,
            scores_by_problem=scores_by_problem,
        )

    def _estimate_acceptance_rate(self) -> float:
        """Parse HELIX state.json files for acceptance rate; fallback to N/A."""
        accepted = proposed = 0
        for state_file in self.run_dir.rglob("state.json"):
            try:
                state = json.loads(state_file.read_text())
                proposed += state.get("total_proposals", 0)
                accepted += state.get("total_accepted", 0)
            except Exception:
                pass
        if proposed > 0:
            return accepted / proposed
        # For GEPA, every evaluate() call is implicitly a "proposal" — we don't
        # have the mutation-level data easily, so return 1.0 as a placeholder.
        return 1.0

    def _estimate_evals_to_best(self, ok_results: list[dict]) -> float:
        """Estimate how many evaluations were needed to reach the best score.
        Approximated from the GEPA log if it records per-eval scores."""
        estimates = []
        for r in ok_results:
            pid = r.get("problem_id")
            gepa_log = self.run_dir / str(pid) / "gepa_log"
            # GEPA writes a lineage.json; parse if it exists
            lineage = gepa_log / "lineage.json" if gepa_log.exists() else None
            if lineage and lineage.exists():
                try:
                    data = json.loads(lineage.read_text())
                    best = r.get("best_score", 0.0)
                    for i, entry in enumerate(data, 1):
                        if entry.get("score", 0.0) >= best * 0.99:
                            estimates.append(float(i))
                            break
                except Exception:
                    pass
        return statistics.mean(estimates) if estimates else float("nan")

    # --------------------------------------------------------------------- #
    # Output
    # --------------------------------------------------------------------- #

    def print_summary(self, label: str = "") -> None:
        m = self.compute(label)
        print(f"\n{'='*65}")
        print(f"Results: {m.label}  |  {m.track}  |  {m.run_tag}")
        print(f"{'='*65}")
        print(f"  Problems  : {m.n_ok}/{m.n_problems} ok  "
              f"({m.n_error} error, {m.n_timeout} timeout)")
        print(f"  Score mean    : {m.score_mean:.4f}  ± {m.score_std:.4f}")
        print(f"  Score median  : {m.score_median:.4f}")
        print(f"  Score max     : {m.score_max:.4f}")
        print(f"  Solve rate    : {m.solve_rate:.1%}  (score > 0)")
        print(f"\n  -- Efficiency --")
        print(f"  Total tokens      : {m.total_tokens:,}")
        print(f"  Tokens/call avg   : {m.tokens_per_mutation_avg:,.1f}")
        print(f"  Prompt fraction   : {m.prompt_tokens_fraction:.1%}  "
              f"(rest=completion/novel)")
        print(f"  Total latency     : {m.total_latency_s:.1f}s")
        print(f"  Latency/call avg  : {m.latency_per_call_avg_s:.3f}s")
        print(f"\n  -- Convergence --")
        print(f"  Acceptance rate   : {m.acceptance_rate:.1%}")
        print(f"  Evals to best avg : {m.evaluations_to_best_avg:.1f}")
        print(f"{'='*65}\n")

    def to_latex_row(self, label: str = "") -> str:
        """One LaTeX table row ready to paste into the paper.

        Columns (matching the paper's Table 1 template):
        System | Score Mean | Score Median | Solve Rate | Tok/Mut | Accept Rate
        """
        m = self.compute(label)
        row = (
            f"{m.label} & "
            f"{m.score_mean:.2f} & "
            f"{m.score_median:.2f} & "
            f"{m.solve_rate:.0%} & "
            f"{int(m.tokens_per_mutation_avg):,} & "
            f"{m.acceptance_rate:.0%} "
            f"\\\\"
        )
        return row

    def to_json(self, label: str = "") -> dict:
        return self.compute(label).__dict__

    def save_json(self, label: str = "") -> pathlib.Path:
        out = self.run_dir / "paper_metrics.json"
        out.write_text(json.dumps(self.to_json(label), indent=2))
        print(f"Saved paper metrics to {out}")
        return out


# --------------------------------------------------------------------------- #
# Comparison helper
# --------------------------------------------------------------------------- #

def compare_runs(
    run_a: str | pathlib.Path,
    run_b: str | pathlib.Path,
    label_a: str = "System A",
    label_b: str = "System B",
    latex: bool = False,
) -> None:
    """Print a side-by-side comparison of two runs — for paper tables."""
    agg_a = ResultsAggregator(run_a)
    agg_b = ResultsAggregator(run_b)
    m_a = agg_a.compute(label_a)
    m_b = agg_b.compute(label_b)

    def _delta(a: float, b: float) -> str:
        if a == 0:
            return "N/A"
        pct = (b - a) / abs(a) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    print(f"\n{'='*80}")
    print(f"Comparison: {label_a}  vs.  {label_b}")
    print(f"{'='*80}")
    header = f"{'Metric':<30} {label_a:>15} {label_b:>15} {'Delta':>10}"
    print(header)
    print("-" * 80)

    rows = [
        ("Score mean",         m_a.score_mean,                 m_b.score_mean),
        ("Score median",       m_a.score_median,               m_b.score_median),
        ("Solve rate",         m_a.solve_rate,                 m_b.solve_rate),
        ("Tokens/call avg",    m_a.tokens_per_mutation_avg,    m_b.tokens_per_mutation_avg),
        ("Prompt fraction",    m_a.prompt_tokens_fraction,     m_b.prompt_tokens_fraction),
        ("Acceptance rate",    m_a.acceptance_rate,            m_b.acceptance_rate),
        ("Evals to best",      m_a.evaluations_to_best_avg,    m_b.evaluations_to_best_avg),
    ]
    for name, va, vb in rows:
        print(f"  {name:<28} {va:>15.4f} {vb:>15.4f} {_delta(va, vb):>10}")

    print("=" * 80)

    if latex:
        print("\n-- LaTeX table rows --")
        print(agg_a.to_latex_row(label_a))
        print(agg_b.to_latex_row(label_b))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description="Aggregate HELIX experiment results")
    ap.add_argument("--run", required=True, help="Path to run directory")
    ap.add_argument("--compare", default=None,
                    help="Second run directory to compare against")
    ap.add_argument("--label", default="", help="Label for --run")
    ap.add_argument("--label-compare", default="", help="Label for --compare")
    ap.add_argument("--latex", action="store_true",
                    help="Print LaTeX table row(s)")
    ap.add_argument("--save", action="store_true",
                    help="Save paper_metrics.json to the run directory")
    args = ap.parse_args()

    agg = ResultsAggregator(args.run)
    agg.print_summary(args.label)

    if args.save:
        agg.save_json(args.label)

    if args.compare:
        compare_runs(
            args.run, args.compare,
            label_a=args.label or pathlib.Path(args.run).name,
            label_b=args.label_compare or pathlib.Path(args.compare).name,
            latex=args.latex,
        )
    elif args.latex:
        print("\n-- LaTeX row --")
        print(agg.to_latex_row(args.label))


if __name__ == "__main__":
    main()
