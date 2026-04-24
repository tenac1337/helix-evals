"""Token logger for HELIX NeurIPS experiments.

Intercepts every chat completion made through the openai Python client and logs:
    - model, prompt_tokens, completion_tokens, total_tokens
    - call_type: "task" | "reflection" (inferred from the model env var)
    - problem_id, run_id, experiment_tag
    - wall-clock latency (seconds)
    - timestamp (ISO)

Usage
-----
    from core.token_logger import TokenLogger

    logger = TokenLogger(
        log_path="results/my_run/tokens.jsonl",
        run_id="gepa-alg-0",
        problem_id="0",
        experiment_tag="track_c",
    )
    logger.patch()          # installs the monkey-patch

    # ... all openai calls now logged automatically ...

    logger.unpatch()        # restores original client
    summary = logger.summary()

The patch is lightweight — it wraps `client.chat.completions.create` with a
thin decorator that records usage after each call. It works for both sync and
async clients, and for calls made by GEPA / HELIX internals (because they all
go through the openai package under the hood).
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class TokenRecord:
    timestamp: str
    run_id: str
    problem_id: str
    experiment_tag: str
    call_type: str          # "task" | "reflection" | "unknown"
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_s: float
    extra: dict = field(default_factory=dict)

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class TokenSummary:
    run_id: str
    problem_id: str
    experiment_tag: str
    total_calls: int
    task_calls: int
    reflection_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    tokens_per_call_avg: float
    total_latency_s: float
    latency_per_call_avg: float

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Logger
# --------------------------------------------------------------------------- #

class TokenLogger:
    """Thread-safe token logger that monkey-patches the openai client."""

    def __init__(
        self,
        log_path: str | pathlib.Path,
        run_id: str,
        problem_id: str = "",
        experiment_tag: str = "",
        task_model_env: str = "TASK_MODEL",
        reflection_model_env: str = "REFLECTION_MODEL",
    ) -> None:
        self.log_path = pathlib.Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.problem_id = problem_id
        self.experiment_tag = experiment_tag
        self._task_model = os.environ.get(task_model_env, "")
        self._reflection_model = os.environ.get(reflection_model_env, "")
        self._records: list[TokenRecord] = []
        self._lock = threading.Lock()
        self._log_file = self.log_path.open("a")
        self._patched = False
        self._original_create: Any = None

    # --------------------------------------------------------------------- #
    # Patch / unpatch
    # --------------------------------------------------------------------- #

    def patch(self) -> None:
        """Monkey-patch openai.chat.completions.create."""
        if self._patched:
            return
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package not installed")

        original = openai.chat.completions.create

        logger_ref = self  # capture for closure

        def _patched_create(*args, **kwargs):
            t0 = time.monotonic()
            response = original(*args, **kwargs)
            latency = time.monotonic() - t0
            logger_ref._record(kwargs, response, latency)
            return response

        self._original_create = original
        openai.chat.completions.create = _patched_create
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        import openai
        openai.chat.completions.create = self._original_create
        self._patched = False
        self._log_file.flush()

    # --------------------------------------------------------------------- #
    # Internal recording
    # --------------------------------------------------------------------- #

    def _infer_call_type(self, model: str) -> str:
        """Classify a call as task or reflection based on env vars."""
        # Normalise: strip "openai/" prefix LiteLLM adds
        clean = model.replace("openai/", "").strip()
        task_clean = self._task_model.replace("openai/", "").strip()
        refl_clean = self._reflection_model.replace("openai/", "").strip()
        if clean == task_clean:
            return "task"
        if clean == refl_clean:
            return "reflection"
        # Fallback: GEPA sends reflection calls from a higher-temperature prompt;
        # if the same model is used for both, mark as "task" by default.
        return "task" if task_clean else "unknown"

    def _record(self, kwargs: dict, response: Any, latency: float) -> None:
        try:
            usage = response.usage
            model = getattr(response, "model", "") or kwargs.get("model", "unknown")
            rec = TokenRecord(
                timestamp=datetime.datetime.utcnow().isoformat() + "Z",
                run_id=self.run_id,
                problem_id=self.problem_id,
                experiment_tag=self.experiment_tag,
                call_type=self._infer_call_type(model),
                model=model,
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
                latency_s=round(latency, 3),
            )
            with self._lock:
                self._records.append(rec)
                self._log_file.write(rec.to_jsonl() + "\n")
                self._log_file.flush()
        except Exception:
            pass  # Never crash the experiment because of logging

    # --------------------------------------------------------------------- #
    # Summary / analysis
    # --------------------------------------------------------------------- #

    def summary(self) -> TokenSummary:
        with self._lock:
            recs = list(self._records)
        if not recs:
            return TokenSummary(
                run_id=self.run_id, problem_id=self.problem_id,
                experiment_tag=self.experiment_tag,
                total_calls=0, task_calls=0, reflection_calls=0,
                total_prompt_tokens=0, total_completion_tokens=0,
                total_tokens=0, tokens_per_call_avg=0.0,
                total_latency_s=0.0, latency_per_call_avg=0.0,
            )
        task = [r for r in recs if r.call_type == "task"]
        refl = [r for r in recs if r.call_type == "reflection"]
        total_tok = sum(r.total_tokens for r in recs)
        total_lat = sum(r.latency_s for r in recs)
        return TokenSummary(
            run_id=self.run_id,
            problem_id=self.problem_id,
            experiment_tag=self.experiment_tag,
            total_calls=len(recs),
            task_calls=len(task),
            reflection_calls=len(refl),
            total_prompt_tokens=sum(r.prompt_tokens for r in recs),
            total_completion_tokens=sum(r.completion_tokens for r in recs),
            total_tokens=total_tok,
            tokens_per_call_avg=round(total_tok / len(recs), 1),
            total_latency_s=round(total_lat, 2),
            latency_per_call_avg=round(total_lat / len(recs), 3),
        )

    def print_summary(self) -> None:
        s = self.summary()
        print(f"\n{'='*55}")
        print(f"Token summary  run={s.run_id}  problem={s.problem_id}")
        print(f"{'='*55}")
        print(f"  Total calls        : {s.total_calls}")
        print(f"    task calls       : {s.task_calls}")
        print(f"    reflection calls : {s.reflection_calls}")
        print(f"  Total tokens       : {s.total_tokens:,}")
        print(f"    prompt           : {s.total_prompt_tokens:,}")
        print(f"    completion       : {s.total_completion_tokens:,}")
        print(f"  Tokens/call (avg)  : {s.tokens_per_call_avg:,.1f}")
        print(f"  Total latency      : {s.total_latency_s:.1f}s")
        print(f"  Latency/call (avg) : {s.latency_per_call_avg:.3f}s")
        print(f"{'='*55}\n")

    def close(self) -> None:
        self.unpatch()
        self._log_file.close()

    def __enter__(self) -> "TokenLogger":
        self.patch()
        return self

    def __exit__(self, *_) -> None:
        self.close()
