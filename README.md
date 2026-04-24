# HELIX: (Hierarchical Evolution via LLM-Informed eXploration) Evaluation Framework

> **Evaluation framework for GEPA and HELIX optimizers on the Frontier-CS algorithmic benchmark.

---

## Overview

This repository contains the experimental infrastructure for the paper **"HELIX: Hierarchical Evolution via LLM-Informed eXploration"**

We evaluate two LLM-guided evolutionary optimizers on the [Frontier-CS](https://github.com/FrontierCS/Frontier-CS) benchmark — a suite of 178 competitive programming problems scored on a continuous scale via Docker-based evaluation.

| Optimizer | Description |
|---|---|
| **GEPA** | Single-completion evolver. Uses a task LM to propose candidate solutions and a reflection LM to analyze feedback and propose mutations. |
| **HELIX** | Whole-repository agentic mutation engine. Uses Claude Code to mutate the entire solution repository across generations. |

---

## Results (Track C — Algorithmic, 172 problems)

| Method | Model | Mean Score | Solve Rate | Max Score |
|---|---|---|---|---|
| GEPA | Qwen3-Coder-480B | TBD | TBD | TBD |
| HELIX | Claude Sonnet 4.5 | TBD | TBD | TBD |
| Reference | Human expert | ~89.1 | 100% | 100 |

*Results will be updated as experiments complete.*

---

## Setup

### Requirements

- Python 3.13+
- Docker Desktop (for Frontier-CS evaluation backend)
- Node.js 18+ (for Claude Code / HELIX)
- [Frontier-CS](https://github.com/FrontierCS/Frontier-CS) cloned locally
- OpenRouter API key (for LLM inference)

### Installation

```bash
# Clone this repo
git clone https://github.com/YOUR_USERNAME/helix-evals
cd helix-evals

# Create venv
python3.13 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install gepa helix-evo litellm openai python-dotenv pyyaml hatchling cloudpickle certifi

# Install Frontier-CS (editable)
pip install -e /path/to/Frontier-CS
```

### Configuration

Copy `.env.template` to `.env` and fill in your keys:

```bash
cp .env.template .env
```

```bash
# LLM inference (OpenRouter)
OPENAI_BASE_URL="https://openrouter.ai/api/v1"
OPENAI_API_KEY="sk-or-your-key"
OPENROUTER_API_KEY="sk-or-your-key"

# Models
TASK_MODEL="openrouter/qwen/qwen3-coder"
REFLECTION_MODEL="openrouter/qwen/qwen3-coder"

# Anthropic (for HELIX's Claude Code engine)
ANTHROPIC_API_KEY="sk-ant-your-key"

# Paths
FRONTIER_CS_REPO="/path/to/Frontier-CS"
RESULTS_DIR="./results"
```

---

## Running Experiments

### Smoke test (1 problem, 5 calls)

```bash
python3 track_c/run_frontier_cs.py \
    --optimizer gepa \
    --n-problems 1 \
    --max-metric-calls 5 \
    --max-workers 1
```

### Full Track C GEPA run (172 problems, overnight)

```bash
mkdir -p logs
nohup .venv/bin/python3 track_c/run_frontier_cs.py \
    --optimizer gepa \
    --n-problems 172 \
    --max-metric-calls 30 \
    --max-workers 4 \
    --label "GEPA Qwen3-Coder-480B" \
    > logs/track_c_gepa_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

### Full Track C HELIX run

```bash
nohup .venv/bin/python3 track_c/run_frontier_cs.py \
    --optimizer helix \
    --n-problems 172 \
    --max-generations 5 \
    --max-evaluations 20 \
    --max-workers 2 \
    --label "HELIX Claude Sonnet 4.5" \
    > logs/track_c_helix_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

### Resume after interruption

```bash
# Find your run_tag
ls -t results/ | head -3

# Resume — completed problems are skipped automatically
.venv/bin/python3 track_c/run_frontier_cs.py \
    --optimizer gepa \
    --n-problems 172 \
    --max-metric-calls 30 \
    --max-workers 4 \
    --run-tag "gepa-algorithmic-YOUR-TIMESTAMP"
```

### Model sweep (ablation)

```bash
python3 track_c/run_frontier_cs.py \
    --optimizer gepa \
    --n-problems 172 \
    --max-metric-calls 30 \
    --use-default-priority
```

---

## Monitoring Progress

```bash
python3 - << 'PY'
import pathlib, json, statistics
run_dir = sorted(pathlib.Path("results").iterdir(), key=lambda p: p.stat().st_mtime)[-1]
results = [json.loads(p.read_text()) for p in run_dir.rglob("result.json")]
ok = [r for r in results if r.get("status") == "ok"]
scores = [r["best_score"] for r in ok]
print(f"Run: {run_dir.name}")
print(f"Completed: {len(ok)}/172")
if scores:
    print(f"Mean:   {statistics.mean(scores):.2f}")
    print(f"Median: {statistics.median(scores):.2f}")
    print(f"Max:    {max(scores):.2f}")
    print(f"Solves: {sum(1 for s in scores if s > 0)}/{len(ok)}")
PY
```

---

## Project Structure

```
helix-evals/
├── core/
│   ├── batch_runner.py       # Parallel runner with resume + retry
│   ├── rate_limiter.py       # Token-bucket rate limiter for free API tiers
│   ├── helix_reader.py       # Parses HELIX .helix/ output files
│   ├── results_aggregator.py # Paper metrics + LaTeX table generation
│   └── token_logger.py       # Token usage tracking
├── track_c/
│   └── run_frontier_cs.py    # Main driver for Track C experiments
├── frontier_adapter.py       # Wraps Frontier-CS SingleEvaluator for GEPA
├── seed_cpp.py               # Trivial C++ seed (prints 0)
├── results/                  # Auto-created — one dir per run
└── logs/                     # nohup log files
```

---

## Resilience Features

The runner is designed for long overnight experiments on a laptop:

- **Per-eval checkpointing** — `progress.json` written after every Docker eval
- **GEPA state resume** — GEPA's `gepa_state.bin` persists across restarts; same `run_dir` = automatic resume from last completed iteration
- **OpenRouter retry + fallback** — exponential backoff on 429/503, then tries fallback models in order, with local Ollama as last resort
- **Partial run resume** — problems with `status: ok` are skipped on restart; failed/timeout problems are retried

---

## Models

| Role | Model | Provider |
|---|---|---|
| Task LM | Qwen3-Coder-480B-A35B | OpenRouter (paid) |
| Reflection LM | Qwen3-Coder-480B-A35B | OpenRouter (paid) |
| HELIX mutation | Claude Sonnet 4.5 | Anthropic API |
| Local fallback | Qwen3-Coder-30B | Ollama (local) |

All models used for GEPA are open-weight (Apache 2.0 or Modified-MIT for research use). HELIX uses Claude Sonnet 4.5 via the Anthropic API.

## License

MIT — see [LICENSE](LICENSE).

Frontier-CS benchmark is subject to its own license. Model weights used via OpenRouter are subject to their respective licenses (Qwen3: Apache 2.0, MiniMax M2.5/M2.7: Modified-MIT for research use).

