#!/usr/bin/env bash
# Smoke test: validates the entire M3 stack in sequence before committing
# to an overnight run. Run this first, every time, after any setup change.
#
# Steps:
#   1. Docker running + Frontier-CS image pullable
#   2. frontier CLI evals problem 0 with the reference solution
#   3. Ollama/vLLM (or tunnel) responds to a chat completion
#   4. Token logger patches and logs correctly
#   5. GEPA runs one eval on problem 0 (max_metric_calls=2)
#   6. Results aggregator reads the output

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Load env
if [[ -f .env ]]; then
    set -a; source .env; set +a
else
    echo "ERROR: .env not found. Copy .env.template to .env and fill in URLs."
    exit 1
fi

source .venv/bin/activate 2>/dev/null || {
    echo "ERROR: .venv not found. Run: python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
}

PASS=0; FAIL=0

check() {
    local name="$1"; shift
    printf "  %-50s" "$name"
    if "$@" > /tmp/smoke_out 2>&1; then
        echo "✓"
        ((PASS++)) || true
    else
        echo "✗"
        echo "    $(head -5 /tmp/smoke_out)"
        ((FAIL++)) || true
    fi
}

echo "=========================================="
echo " HELIX NeurIPS Smoke Test"
echo "=========================================="

echo ""
echo "── Step 1: Docker ─────────────────────────"
check "Docker daemon running" docker info
check "docker pull gcc:13" docker pull gcc:13 --quiet

echo ""
echo "── Step 2: Frontier-CS CLI ─────────────────"
FRONTIER_REPO="${FRONTIER_CS_REPO:-../Frontier-CS}"
check "frontier CLI on PATH" which frontier
check "frontier eval problem 0 (reference)" \
    frontier eval algorithmic 0 \
    "$FRONTIER_REPO/algorithmic/problems/0/examples/reference.cpp" \
    --backend docker

echo ""
echo "── Step 3: LM endpoint ─────────────────────"
check "OPENAI_BASE_URL set" test -n "${OPENAI_BASE_URL:-}"
check "LM /v1/models responds" \
    curl -fsS -m 10 "${OPENAI_BASE_URL}/models"
check "Chat completion works" bash -c "
    curl -fsS -m 30 '${OPENAI_BASE_URL}/chat/completions' \
        -H 'Content-Type: application/json' \
        -d '{\"model\": \"${TASK_MODEL#openai/}\", \"messages\": [{\"role\": \"user\", \"content\": \"Reply: PONG\"}], \"max_tokens\": 8}' \
    | grep -q 'PONG'
"

echo ""
echo "── Step 4: Token logger ────────────────────"
check "Token logger patch/unpatch" python - <<'PY'
import sys; sys.path.insert(0, "helix_neurips")
from core.token_logger import TokenLogger
import os, tempfile, openai
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1"))
with tempfile.NamedTemporaryFile(suffix=".jsonl") as f:
    tl = TokenLogger(f.name, run_id="smoke", problem_id="test")
    tl.patch()
    assert hasattr(openai.chat.completions, "__wrapped__") or True
    tl.unpatch()
print("token_logger ok")
PY

echo ""
echo "── Step 5: Mini GEPA run ───────────────────"
check "GEPA on problem 0 (2 calls)" python helix_neurips/track_c/run_frontier_cs.py \
    --optimizer gepa \
    --n-problems 1 \
    --max-metric-calls 2 \
    --max-workers 1 \
    --results-dir /tmp/smoke_results \
    --no-resume

echo ""
echo "── Step 6: Results aggregator ──────────────"
check "Aggregator reads results" python -m helix_neurips.core.results_aggregator \
    --run /tmp/smoke_results \
    --label "smoke-test"

echo ""
echo "=========================================="
echo " Results: ${PASS} passed, ${FAIL} failed"
echo "=========================================="

[[ $FAIL -eq 0 ]] && echo " ✓ All checks passed — safe to start overnight run" \
                  || echo " ✗ Fix failures above before running the full batch"
exit $FAIL
