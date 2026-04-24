"""Adapter bridging GEPA to Frontier-CS via Docker on M3."""
from __future__ import annotations
import dataclasses, os, sys, traceback
from typing import Any

_FRONTIER_REPO = os.environ.get("FRONTIER_CS_REPO", "../Frontier-CS")
_FRONTIER_SRC = os.path.join(os.path.expanduser(_FRONTIER_REPO), "src")
if _FRONTIER_SRC not in sys.path:
    sys.path.insert(0, _FRONTIER_SRC)

from frontier_cs import SingleEvaluator  # type: ignore

_SINGLETON_EVALUATOR = None

def _get_evaluator() -> SingleEvaluator:
    global _SINGLETON_EVALUATOR
    if _SINGLETON_EVALUATOR is None:
        _SINGLETON_EVALUATOR = SingleEvaluator()
    return _SINGLETON_EVALUATOR

def warm_evaluator() -> None:
    _get_evaluator()

@dataclasses.dataclass(frozen=True)
class FrontierTask:
    track: str
    problem_id: int | str
    language: str = "cpp"

    @property
    def key(self) -> str:
        return f"{self.track}:{self.problem_id}"

class FrontierCSAdapter:
    def __init__(self, backend: str = "docker") -> None:
        self._backend = backend

    @property
    def _evaluator(self) -> SingleEvaluator:
        return _get_evaluator()

    def evaluate(self, candidate_code: str, task: FrontierTask) -> tuple[float, str]:
        try:
            result: Any = self._evaluator.evaluate(
                task.track,
                problem_id=task.problem_id,
                code=candidate_code,
                backend=self._backend,
            )
        except Exception as exc:
            return 0.0, f"EXCEPTION ({type(exc).__name__}): {exc}\n{traceback.format_exc()}"

        # score_unbounded exists as an attribute but NOT as a kwarg
        # Both score_unbounded and score can be None if Docker eval fails
        raw = getattr(result, "score_unbounded", None)
        if raw is None:
            raw = getattr(result, "score", None)
        score = float(raw) if raw is not None else 0.0
        asi = self._build_asi(result, score, task)
        return score, asi

    def make_optimize_anything_evaluator(self, tasks: list[FrontierTask]):
        if len(tasks) == 1:
            only = tasks[0]
            def _single(candidate: str) -> tuple:
                score, asi = self.evaluate(candidate, only)
                return score, {"asi": asi}
            return _single
        def _multi(candidate: str, task: FrontierTask) -> tuple:
            score, asi = self.evaluate(candidate, task)
            return score, {"asi": asi}
        return _multi

    def _build_asi(self, result: Any, score: float, task: FrontierTask) -> str:
        parts = [f"Task: {task.key}", f"Score: {score:.4f}"]

        # Include status and result message
        for attr in ("message", "logs"):
            v = getattr(result, attr, None)
            if v:
                parts.append(f"--- {attr} ---\n{str(v)[:1000]}")

        # Include per-test-case feedback — critical for reflection LM
        metadata = getattr(result, "metadata", None)
        if metadata:
            cases = metadata.get("cases", []) if isinstance(metadata, dict) else []
            if cases:
                lines = ["--- test cases ---"]
                for i, c in enumerate(cases[:10]):
                    status = c.get("status", "?")
                    msg = c.get("msg", "")[:200]
                    out = c.get("output", "")[:100]
                    ratio = c.get("scoreRatio", 0)
                    lines.append(f"  case {i}: {status}  score_ratio={ratio}  output={repr(out)}  msg={msg}")
                parts.append("\n".join(lines))

        return "\n\n".join(parts)
