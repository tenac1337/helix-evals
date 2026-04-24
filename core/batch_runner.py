"""Parallel batch runner — resilient GEPA/HELIX experiments."""
from __future__ import annotations
import concurrent.futures, datetime, json, logging, os, pathlib
import statistics, sys, time, traceback
from dataclasses import dataclass, field, asdict
from typing import Optional
import pathlib as _pathlib
from dotenv import load_dotenv

# Load from project root .env, overriding any stale shell exports
_ENV_PATH = _pathlib.Path(__file__).parent.parent / '.env'
load_dotenv(_ENV_PATH, override=True)

# Fix SSL certificates for Python 3.13 on macOS
try:
    import ssl as _ssl, certifi as _certifi
    _ssl._create_default_https_context = lambda: _ssl.create_default_context(
        cafile=_certifi.where()
    )
except Exception:
    pass
logger = logging.getLogger(__name__)

REFLECTION_FALLBACKS = [
    "openrouter/qwen/qwen3-coder",       # 480B paid — primary fallback
    "openrouter/qwen/qwen3-coder:free",  # 480B free — secondary fallback
    "ollama/qwen3-coder:30b",            # local 30B — last resort
]
_LITELLM_PATCHED = False

def _patch_litellm_with_retry(fallback_models: list) -> None:
    global _LITELLM_PATCHED
    if _LITELLM_PATCHED:
        return
    try:
        import litellm as _lm
    except ImportError:
        return
    _original = _lm.completion
    def _resilient(model, messages, **kwargs):
        models_to_try = [model] + [m for m in fallback_models if m != model]
        last_exc = None
        for attempt, try_model in enumerate(models_to_try):
            retries = 2 if attempt == 0 else 1
            for retry in range(retries):
                try:
                    return _original(model=try_model, messages=messages, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc).lower()
                    if not any(k in msg for k in ("429","rate limit","too many",
                            "provider returned error","quota","capacity","500","502","503","timeout")):
                        raise
                    if retry < retries - 1:
                        delay = 5.0 * (2 ** retry)
                        logger.warning("LLM %s retry %d/4 in %.0fs: %s", try_model, retry+1, delay, exc)
                        time.sleep(delay)
                    else:
                        logger.warning("LLM %s exhausted, trying fallback: %s", try_model, exc)
        raise last_exc
    _lm.completion = _resilient
    _LITELLM_PATCHED = True
    logger.info("litellm patched: retry+%d fallbacks", len(fallback_models))


@dataclass
class RunConfig:
    optimizer: str
    track: str
    problem_ids: list[int | str]
    task_model: str = ""
    reflection_model: str = ""
    helix_claude_model: str = "sonnet"
    max_metric_calls: int = 30
    max_generations: int = 5
    max_evaluations: int = 20
    max_turns: int = 10
    max_workers: int = 4
    run_tag: str = ""
    results_root: str = "results"
    resume: bool = True
    timeout_per_problem: int = 1800
    experiment_tag: str = "track_c"

    def __post_init__(self) -> None:
        if not self.run_tag:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            t = (self.task_model or os.environ.get("TASK_MODEL","default")).split("/")[-1]
            r = (self.reflection_model or os.environ.get("REFLECTION_MODEL","default")).split("/")[-1]
            t = t.replace(":free","").replace(":","")
            r = r.replace(":free","").replace(":","")
            self.run_tag = f"{self.optimizer}-{self.track}-{t}_x_{r}-{ts}"

    def effective_task_model(self) -> str:
        return self.task_model or os.environ.get("TASK_MODEL","openrouter/openai/gpt-oss-120b:free")

    def effective_reflection_model(self) -> str:
        return self.reflection_model or os.environ.get("REFLECTION_MODEL","openrouter/minimax/minimax-m2.5:free")


@dataclass
class ProblemResult:
    problem_id: int | str
    track: str
    optimizer: str
    status: str
    best_score: float = 0.0
    token_summary: dict = field(default_factory=dict)
    duration_s: float = 0.0
    error: Optional[str] = None
    best_candidate_path: Optional[str] = None
    run_tag: str = ""
    task_model: str = ""
    reflection_model: str = ""
    eval_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class BatchRunner:
    def __init__(self, cfg: RunConfig) -> None:
        self.cfg = cfg
        self.results_root = pathlib.Path(cfg.results_root) / cfg.run_tag
        self.results_root.mkdir(parents=True, exist_ok=True)
        (self.results_root / "run_config.json").write_text(json.dumps(asdict(cfg), indent=2))
        self._results: list[ProblemResult] = []
        self._limiter = None

    def run(self) -> list[ProblemResult]:
        self._install_rate_limiter()
        self._install_litellm_retry()
        if self.cfg.optimizer == "gepa":
            _root = str(pathlib.Path(__file__).parent.parent)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from frontier_adapter import warm_evaluator
            warm_evaluator()
        cfg = self.cfg
        print(f"\nBatchRunner: {cfg.optimizer.upper()} — {len(cfg.problem_ids)} {cfg.track} problems")
        print(f"  run_tag          : {cfg.run_tag}")
        print(f"  task_model       : {cfg.effective_task_model()}")
        print(f"  reflection_model : {cfg.effective_reflection_model()}")
        print(f"  results          : {self.results_root}")
        print(f"  workers          : {cfg.max_workers}")
        print(f"  budget           : max_metric_calls={cfg.max_metric_calls}  timeout={cfg.timeout_per_problem}s")
        print(f"  resume           : {cfg.resume}")
        if self._limiter:
            s = self._limiter.status()
            print(f"  rate_limiter     : {s['provider']}  rpm={s['rpm_cap']}  daily={s['daily_cap']}")
        print()
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
            futures = {pool.submit(self._run_one_safe, pid): pid for pid in cfg.problem_ids}
            for future in concurrent.futures.as_completed(futures):
                pid = futures[future]
                result = future.result()
                self._results.append(result)
                self._log_result(result)
                icon = "✓" if result.status=="ok" else "↩" if result.status=="skipped" else "✗"
                print(f"  {icon} [{pid}] {result.status}  score={result.best_score:.4f}  "
                      f"dur={result.duration_s:.0f}s  evals={result.eval_count}")
        return self._results

    def print_summary(self) -> None:
        ok = [r for r in self._results if r.status == "ok"]
        err = [r for r in self._results if r.status == "error"]
        timeout = [r for r in self._results if r.status == "timeout"]
        skipped = [r for r in self._results if r.status == "skipped"]
        scores = [r.best_score for r in ok]
        print(f"\n{'='*65}")
        print(f"Batch summary  {self.cfg.run_tag}")
        print(f"{'='*65}")
        print(f"  Problems : {len(self._results)}  ok={len(ok)}  err={len(err)}  timeout={len(timeout)}  skip={len(skipped)}")
        if scores:
            print(f"  Score mean   : {statistics.mean(scores):.4f}")
            print(f"  Score median : {statistics.median(scores):.4f}")
            print(f"  Score max    : {max(scores):.4f}")
            print(f"  Solves >0    : {sum(1 for s in scores if s>0)}/{len(scores)}")
        print(f"{'='*65}\n")
        agg = {
            "run_tag": self.cfg.run_tag, "optimizer": self.cfg.optimizer,
            "track": self.cfg.track,
            "task_model": self.cfg.effective_task_model(),
            "reflection_model": self.cfg.effective_reflection_model(),
            "n_total": len(self._results), "n_ok": len(ok), "n_error": len(err),
            "n_timeout": len(timeout), "n_skipped": len(skipped),
            "score_mean": statistics.mean(scores) if scores else 0.0,
            "score_median": statistics.median(scores) if scores else 0.0,
            "score_max": max(scores) if scores else 0.0,
            "scores_by_problem": {str(r.problem_id): r.best_score for r in ok},
        }
        out = self.results_root / "aggregate.json"
        out.write_text(json.dumps(agg, indent=2))
        print(f"Aggregate saved to {out}")

    def _install_rate_limiter(self) -> None:
        base_url = os.environ.get("OPENAI_BASE_URL","")
        if "localhost" in base_url or "127.0.0.1" in base_url:
            return
        from core.rate_limiter import patch_openai_with_rate_limit
        self._limiter = patch_openai_with_rate_limit()

    def _install_litellm_retry(self) -> None:
        reflection = self.cfg.effective_reflection_model()
        fallbacks = [reflection] + [m for m in REFLECTION_FALLBACKS if m != reflection]
        _patch_litellm_with_retry(fallbacks)

    def _run_one_safe(self, problem_id: int | str) -> ProblemResult:
        result_path = self.results_root / str(problem_id) / "result.json"
        if self.cfg.resume and result_path.exists():
            try:
                data = json.loads(result_path.read_text())
                if data.get("status") == "ok":
                    fields = ProblemResult.__dataclass_fields__
                    r = ProblemResult(**{k: data[k] for k in fields if k in data})
                    r.status = "skipped"
                    return r
            except Exception:
                pass
        t0 = time.monotonic()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as inner:
                result = inner.submit(self._run_one, problem_id).result(
                    timeout=self.cfg.timeout_per_problem)
        except concurrent.futures.TimeoutError:
            result = ProblemResult(problem_id=problem_id, track=self.cfg.track,
                optimizer=self.cfg.optimizer, status="timeout",
                duration_s=time.monotonic()-t0, run_tag=self.cfg.run_tag,
                error=f"Exceeded {self.cfg.timeout_per_problem}s")
        except Exception as exc:
            result = ProblemResult(problem_id=problem_id, track=self.cfg.track,
                optimizer=self.cfg.optimizer, status="error",
                duration_s=time.monotonic()-t0, run_tag=self.cfg.run_tag,
                error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result.to_dict(), indent=2))
        return result

    def _run_one(self, problem_id: int | str) -> ProblemResult:
        t0 = time.monotonic()
        pid_dir = self.results_root / str(problem_id)
        pid_dir.mkdir(parents=True, exist_ok=True)
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
        from core.token_logger import TokenLogger
        with TokenLogger(log_path=pid_dir/"tokens.jsonl",
                         run_id=f"{self.cfg.run_tag}-{problem_id}",
                         problem_id=str(problem_id),
                         experiment_tag=self.cfg.experiment_tag) as tlog:
            if self.cfg.optimizer == "gepa":
                best_score, best_path, eval_count = self._run_gepa(problem_id, pid_dir)
            elif self.cfg.optimizer == "helix":
                best_score, best_path = self._run_helix(problem_id, pid_dir)
                eval_count = 0
            else:
                raise ValueError(f"Unknown optimizer: {self.cfg.optimizer!r}")
            tok_summary = tlog.summary().to_dict()
        return ProblemResult(
            problem_id=problem_id, track=self.cfg.track,
            optimizer=self.cfg.optimizer, status="ok",
            best_score=best_score, token_summary=tok_summary,
            duration_s=round(time.monotonic()-t0, 2),
            best_candidate_path=str(best_path) if best_path else None,
            run_tag=self.cfg.run_tag,
            task_model=self.cfg.effective_task_model(),
            reflection_model=self.cfg.effective_reflection_model(),
            eval_count=eval_count)

    def _run_gepa(self, problem_id, out_dir):
        from gepa.optimize_anything import (
            optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig)
        from frontier_adapter import FrontierCSAdapter, FrontierTask
        from seed_cpp import SEED_CPP

        task = FrontierTask(track=self.cfg.track, problem_id=problem_id,
            language="cpp" if self.cfg.track=="algorithmic" else "python")
        adapter = FrontierCSAdapter(backend="docker")

        # Stable run_dir — GEPA saves gepa_state.bin after every iteration
        # Same path on restart = automatic resume from last completed iteration
        gepa_log_dir = out_dir / "gepa_log"
        checkpoint_path = out_dir / "progress.json"

        if (gepa_log_dir / "gepa_state.bin").exists():
            try:
                try:

                    print(f"  [{problem_id}] Resuming GEPA from saved state", file=sys.stderr, flush=True)

                except Exception:

                    pass
            except Exception:
                pass

        eval_counter = [0]
        best_so_far = [0.0]
        if checkpoint_path.exists():
            try:
                ckpt = json.loads(checkpoint_path.read_text())
                best_so_far[0] = float(ckpt.get("best_score", 0.0))
                eval_counter[0] = int(ckpt.get("eval_count", 0))
            except Exception:
                pass

        def evaluator(candidate: str) -> tuple:
            score, asi = adapter.evaluate(candidate, task)
            eval_counter[0] += 1
            if score > best_so_far[0]:
                best_so_far[0] = score
            try:
                print(f"  [{problem_id}] eval={eval_counter[0]}  "
                      f"score={score:.4f}  best={best_so_far[0]:.4f}",
                      file=sys.stderr, flush=True)
            except Exception:
                pass
            # Write checkpoint after every eval — survives power loss
            try:
                checkpoint_path.write_text(json.dumps({
                    "problem_id": str(problem_id),
                    "eval_count": eval_counter[0],
                    "best_score": best_so_far[0],
                    "last_score": score,
                    "timestamp": time.time(),
                    "status": "running",
                }, indent=2))
            except Exception:
                pass
            return score, {"asi": asi, "problem_id": str(problem_id)}

        # Use configured reflection model (OpenRouter with retry/fallback)
        reflection_lm = self.cfg.effective_reflection_model()
        try:
            try:

                print(f"  [{problem_id}] reflection_lm: {reflection_lm}", file=sys.stderr, flush=True)

            except Exception:

                pass
        except Exception:
            pass
        # Ollama is in REFLECTION_FALLBACKS as last resort — no need to auto-detect

        gepa_cfg = GEPAConfig(
            engine=EngineConfig(
                max_metric_calls=self.cfg.max_metric_calls,
                run_dir=str(gepa_log_dir),
                parallel=False),
            reflection=ReflectionConfig(reflection_lm=reflection_lm))

        # Load problem statement
        frontier_repo = os.environ.get("FRONTIER_CS_REPO", "../Frontier-CS")
        stmt = pathlib.Path(frontier_repo).expanduser() / "algorithmic" / "problems" / str(problem_id) / "statement.txt"
        problem_statement = stmt.read_text()[:3000] if stmt.exists() else f"Problem {problem_id}"

        objective = (
            "You are writing a C++ solution for a competitive programming problem.\n"
            "COMPILER: g++ -std=c++17 on GCC 11, Linux aarch64.\n"
            "OUTPUT FORMAT (critical — wrong format scores 0):\n"
            "  Line 1: W H (width and height of bounding rectangle, integers >= 1)\n"
            "  Lines 2..N+1: X Y R F for each polyomino (translation X Y, rotation R in 0-3, flip F in 0-1)\n"
            "  W and H must be >= 1. Output exactly N+1 lines total.\n\n"
            "PROBLEM STATEMENT:\n" + problem_statement +
            "\n\nSCORING: partial credit for valid placements. Any valid output scores > 0. "
            "Start simple — place pieces in a row, then optimize. "
            "Use compiler errors and per-test-case feedback to fix issues.")

        result = optimize_anything(seed_candidate=SEED_CPP, evaluator=evaluator,
                                   objective=objective, config=gepa_cfg)

        # Extract best score and candidate from GEPAResult
        best_score = 0.0
        best_idx = 0
        scores = getattr(result, "val_aggregate_scores", None) or []
        if scores:
            best_score = float(max(scores))
            best_idx = scores.index(max(scores))

        best_candidate_str = None
        candidates = getattr(result, "candidates", None) or []
        if candidates:
            entry = candidates[min(best_idx, len(candidates)-1)]
            str_key = getattr(result, "_str_candidate_key", "current_candidate")
            best_candidate_str = entry.get(str_key) if isinstance(entry, dict) else str(entry)

        best_path = out_dir / "best_candidate.cpp"
        if best_candidate_str:
            best_path.write_text(best_candidate_str)

        checkpoint_path.write_text(json.dumps({
            "problem_id": str(problem_id), "eval_count": eval_counter[0],
            "best_score": best_score, "timestamp": time.time(), "status": "done"
        }, indent=2))

        return best_score, best_path, eval_counter[0]

    def _run_helix(self, problem_id, out_dir):
        import subprocess
        proj = out_dir / "helix_project"
        adapter_dir = str(pathlib.Path(__file__).parent.parent.resolve())
        self._write_helix_project(proj, problem_id, adapter_dir)
        env = os.environ.copy()
        with open(out_dir / "helix_stdout.log", "w") as log_f:
            subprocess.call(["helix", "evolve"], cwd=proj, env=env,
                            stdout=log_f, stderr=subprocess.STDOUT)
        from core.helix_reader import HelixReader
        reader = HelixReader(proj/".helix", proxy_log=os.environ.get("LITELLM_PROXY_LOG"))
        best_score = reader.best_score()
        subprocess.call(["helix", "best", "--export", str(out_dir/"helix_best")],
                        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        best_path = None
        candidate_path = out_dir / "helix_best" / "solve.cpp"
        if candidate_path.exists():
            best_path = candidate_path
        return best_score, best_path

    def _write_helix_project(self, proj, problem_id, adapter_dir):
        import subprocess
        proj.mkdir(parents=True, exist_ok=True)
        (proj/"helix.toml").write_text("\n".join([
            f'objective = "Maximize Frontier-CS score for problem {problem_id}."',
            '', 'seed = "."', 'rng_seed = 0', '',
            '[evaluator]', 'command = "python evaluate.py"', 'score_parser = "json_score"',
            'include_stdout = true', 'include_stderr = true',
            'protected_files = ["evaluate.py", "problem.json"]', '',
            '[evolution]', f'max_generations = {self.cfg.max_generations}',
            f'max_evaluations = {self.cfg.max_evaluations}',
            'merge_enabled = false', 'minibatch_size = 1', 'cache_evaluation = true',
            'acceptance_criterion = "strict_improvement"', '',
            '[claude]', f'model = "{self.cfg.helix_claude_model}"', 'effort = "medium"',
            f'max_turns = {self.cfg.max_turns}',
            'allowed_tools = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]',
            'background = "Only modify solve.cpp."', '', '[worktree]',
            'base_dir = ".helix/worktrees"']) + "\n")
        (proj/"evaluate.py").write_text(
            "import json, pathlib, sys, traceback\n"
            f"sys.path.insert(0, {repr(adapter_dir)})\n"
            "from frontier_adapter import FrontierCSAdapter, FrontierTask\n"
            "root = pathlib.Path(__file__).parent\n"
            "spec = json.loads((root/'problem.json').read_text())\n"
            "code = (root/'solve.cpp').read_text()\n"
            "try:\n"
            "    adapter = FrontierCSAdapter(backend='docker')\n"
            "    score, asi = adapter.evaluate(code, FrontierTask(\n"
            "        track=spec['track'], problem_id=spec['problem_id'], language='cpp'))\n"
            "    print(json.dumps({'score': score, 'instance_scores': {str(spec['problem_id']): score}, 'asi': asi[:4000]}))\n"
            "except Exception as exc:\n"
            "    print(json.dumps({'score': 0.0, 'instance_scores': {str(spec['problem_id']): 0.0},\n"
            "        'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc()}))\n")
        (proj/"problem.json").write_text(json.dumps(
            {"track": self.cfg.track, "problem_id": problem_id, "backend": "docker"}, indent=2))
        from seed_cpp import SEED_CPP
        (proj/"solve.cpp").write_text(SEED_CPP)
        if not (proj/".git").exists():
            subprocess.run(["git","init","-q"], cwd=proj, check=True)
            subprocess.run(["git","add","-A"], cwd=proj, check=True)
            subprocess.run(["git","-c","user.email=x@x","-c","user.name=x",
                            "commit","-q","-m","init"], cwd=proj, check=True)

    def _log_result(self, result: ProblemResult) -> None:
        path = self.results_root / str(result.problem_id) / "result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.to_dict(), indent=2))
