"""Reads HELIX's output files and extracts paper metrics correctly.

Two problems this module solves:

1. CORRECT SCORE EXTRACTION.
   `batch_runner.py`'s original `state.json` parsing was speculative.
   The reliable approach:
     a) Check `.helix/evaluations/` — each file is an EvalResult JSON with
        a `score` field. Best score = max across all evaluation files.
     b) Fall back to running `helix best` and parsing its stdout.
     c) Last resort: parse `state.json` frontier list (schema is fragile).

2. CLAUDE CODE TOKEN COUNTING.
   HELIX's mutation engine (Claude Code) is a Node.js subprocess.
   It makes Anthropic API calls independently of our Python process,
   so `token_logger.py`'s openai monkey-patch never sees those calls.

   Fix: read the LiteLLM proxy's request log, which captures every
   call regardless of which process made it. The proxy writes to
   `/content/litellm_proxy.log` (Colab) or wherever you pointed it.
   We parse those logs and add them to the token summary.

   If no proxy log is available (pure Ollama / direct Anthropic),
   we fall back to reading Claude Code's `~/.claude/logs/` directory,
   which Claude Code writes per-session usage JSON to.

Usage
-----
    from core.helix_reader import HelixReader
    reader = HelixReader("/path/to/helix_project/.helix")
    print(reader.best_score())
    print(reader.token_summary())
    print(reader.acceptance_rate())
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
from typing import Optional


class HelixReader:
    """Reads a completed (or in-progress) HELIX run's .helix/ directory."""

    def __init__(
        self,
        helix_dir: str | pathlib.Path,
        proxy_log: Optional[str | pathlib.Path] = None,
    ) -> None:
        self.helix_dir = pathlib.Path(helix_dir)
        # proxy_log: path to LiteLLM proxy log file (Colab: /content/litellm_proxy.log)
        self.proxy_log = pathlib.Path(proxy_log) if proxy_log else None

    # --------------------------------------------------------------------- #
    # Score extraction
    # --------------------------------------------------------------------- #

    def best_score(self) -> float:
        """Return the best score seen across all evaluations."""
        # Method A: scan evaluations/ directory (most reliable)
        score = self._score_from_evaluations()
        if score is not None:
            return score

        # Method B: run `helix best` and parse stdout
        score = self._score_from_helix_best()
        if score is not None:
            return score

        # Method C: parse state.json (fragile, schema may change)
        return self._score_from_state_json() or 0.0

    def _score_from_evaluations(self) -> Optional[float]:
        evals_dir = self.helix_dir / "evaluations"
        if not evals_dir.exists():
            return None
        best = None
        for f in evals_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                # EvalResult has: scores (dict), instance_scores (dict), ...
                # For json_score parser: scores = {"score": float}
                s = data.get("scores", {}).get("score")
                if s is None:
                    # json_accuracy parser: scores = {"accuracy": float}
                    s = data.get("scores", {}).get("accuracy")
                if s is None:
                    # Flat score field
                    s = data.get("score")
                if s is not None and (best is None or float(s) > best):
                    best = float(s)
            except Exception:
                pass
        return best

    def _score_from_helix_best(self) -> Optional[float]:
        proj_dir = self.helix_dir.parent
        try:
            out = subprocess.check_output(
                ["helix", "best"], cwd=proj_dir, text=True,
                stderr=subprocess.DEVNULL, timeout=10,
            )
            # helix best prints something like:
            # Best candidate: g3-m2  score=0.7234  ...
            m = re.search(r"score[=:\s]+([0-9.]+)", out, re.IGNORECASE)
            if m:
                return float(m.group(1))
        except Exception:
            pass
        return None

    def _score_from_state_json(self) -> Optional[float]:
        state_file = self.helix_dir / "state.json"
        if not state_file.exists():
            return None
        try:
            state = json.loads(state_file.read_text())
            # Try common field names HELIX might use
            for key in ("best_score", "best_val_score", "top_score"):
                if key in state:
                    return float(state[key])
            # Try frontier list
            frontier = state.get("frontier", [])
            if frontier:
                scores = []
                for c in frontier:
                    for score_key in ("score", "val_score", "aggregate_score"):
                        if score_key in c:
                            scores.append(float(c[score_key]))
                            break
                if scores:
                    return max(scores)
        except Exception:
            pass
        return None

    # --------------------------------------------------------------------- #
    # Acceptance rate
    # --------------------------------------------------------------------- #

    def acceptance_rate(self) -> Optional[float]:
        """Fraction of proposed mutations that passed the train-gate."""
        # HELIX log files: .helix/log/g<N>-m<N>.json or g<N>-x<N>.json
        log_dir = self.helix_dir / "log"
        if not log_dir.exists():
            return None
        proposed = accepted = 0
        for f in log_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                proposed += 1
                # A mutation log entry has an "accepted" or "outcome" field
                if data.get("accepted") is True:
                    accepted += 1
                elif data.get("outcome") in ("accepted", "pareto_update"):
                    accepted += 1
            except Exception:
                pass
        return (accepted / proposed) if proposed > 0 else None

    # --------------------------------------------------------------------- #
    # Token counts — Claude Code via proxy log or ~/.claude/logs/
    # --------------------------------------------------------------------- #

    def claude_token_summary(self) -> dict:
        """Extract token usage for Claude Code mutations.

        Returns a dict with prompt_tokens, completion_tokens, total_tokens,
        n_calls, and source ("proxy_log" | "claude_logs" | "unavailable").
        """
        # Try proxy log first
        if self.proxy_log and self.proxy_log.exists():
            result = self._tokens_from_proxy_log()
            if result["n_calls"] > 0:
                result["source"] = "proxy_log"
                return result

        # Try Claude Code's own usage logs (~/.claude/logs/)
        result = self._tokens_from_claude_logs()
        if result["n_calls"] > 0:
            result["source"] = "claude_logs"
            return result

        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "n_calls": 0,
            "source": "unavailable",
            "note": (
                "Claude Code token counts not available. "
                "Run with LiteLLM proxy and set proxy_log= to get accurate counts."
            ),
        }

    def _tokens_from_proxy_log(self) -> dict:
        """Parse LiteLLM proxy log for token usage lines."""
        prompt = completion = total = n = 0
        # LiteLLM logs lines like:
        # INFO: ... usage: Usage(prompt_tokens=1842, completion_tokens=312, total_tokens=2154)
        pattern = re.compile(
            r"prompt_tokens=(\d+).*?completion_tokens=(\d+).*?total_tokens=(\d+)"
        )
        try:
            for line in self.proxy_log.read_text(errors="replace").splitlines():
                m = pattern.search(line)
                if m:
                    prompt += int(m.group(1))
                    completion += int(m.group(2))
                    total += int(m.group(3))
                    n += 1
        except Exception:
            pass
        return {"prompt_tokens": prompt, "completion_tokens": completion,
                "total_tokens": total, "n_calls": n}

    def _tokens_from_claude_logs(self) -> dict:
        """Read Claude Code's per-session usage JSON from ~/.claude/logs/."""
        prompt = completion = total = n = 0
        claude_logs = pathlib.Path.home() / ".claude" / "logs"
        if not claude_logs.exists():
            return {"prompt_tokens": 0, "completion_tokens": 0,
                    "total_tokens": 0, "n_calls": 0}
        # Claude Code writes session-level usage JSONs
        for f in sorted(claude_logs.rglob("*.json")):
            try:
                data = json.loads(f.read_text())
                usage = data.get("usage") or data.get("token_usage") or {}
                p = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
                c = usage.get("output_tokens") or usage.get("completion_tokens", 0)
                t = usage.get("total_tokens") or (p + c)
                if p or c:
                    prompt += int(p)
                    completion += int(c)
                    total += int(t)
                    n += 1
            except Exception:
                pass
        return {"prompt_tokens": prompt, "completion_tokens": completion,
                "total_tokens": total, "n_calls": n}

    # --------------------------------------------------------------------- #
    # Combined summary for the paper
    # --------------------------------------------------------------------- #

    def full_summary(self) -> dict:
        """All metrics in one dict, ready for results_aggregator."""
        best = self.best_score()
        accept = self.acceptance_rate()
        claude_tok = self.claude_token_summary()
        return {
            "best_score": best,
            "acceptance_rate": accept,
            "claude_code_tokens": claude_tok,
            "helix_dir": str(self.helix_dir),
        }
