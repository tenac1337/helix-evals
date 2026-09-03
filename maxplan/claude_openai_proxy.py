#!/usr/bin/env python3
"""An OpenAI-compatible /v1/chat/completions endpoint backed by the Claude CLI.

Purpose: run SkyDiscover's own baselines -- AdaEvolve, EvoX, OpenEvolve,
ShinkaEvolve -- on the Max plan, with no API key.

SkyDiscover talks OpenAI over HTTP and reads an arbitrary api_base (its vllm and
ollama providers deliberately hardcode none). So it does not need a real OpenAI
endpoint, only something that speaks the protocol. This proxies each request to
`claude --print`, which authenticates against the Max subscription.

Why it matters: the HELIX draft baselines Track B against GEPA, but AdaEvolve,
EvoX, ShinkaEvolve and eps-MemEvo all beat GEPA on every published benchmark.
Comparing against GEPA and calling it the state of the art will not survive
review. This makes the stronger comparison runnable.

    python3 claude_openai_proxy.py --port 8117 --model sonnet
    # then point skydiscover at:  api_base=http://127.0.0.1:8117/v1
"""
from __future__ import annotations
import argparse, json, os, subprocess, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ARGS = None
_LOCK = threading.Semaphore(4)      # cap concurrent CLI invocations
_STATS = {"calls": 0, "errors": 0, "retries": 0}


def call_claude(prompt: str, model: str) -> str:
    env = dict(os.environ)
    env.setdefault("USER", os.environ.get("USER", ""))
    cmd = ["claude", "--print", "--output-format", "json",
           "--model", model, "--max-turns", "1", "--tools", ""]
    last = ""
    for attempt in range(4):
        with _LOCK:
            try:
                p = subprocess.run(cmd, input=prompt, capture_output=True,
                                   text=True, timeout=ARGS.timeout, env=env)
                d = json.loads(p.stdout)
                if d.get("is_error"):
                    last = str(d.get("result", ""))[:200]
                    low = last.lower()
                    if "rate limit" in low or "usage limit" in low or "you've hit" in low:
                        _STATS["retries"] += 1
                        time.sleep(20 * (attempt + 1))
                        continue
                    raise RuntimeError(last)
                return d.get("result", "") or ""
            except subprocess.TimeoutExpired:
                last = f"timeout after {ARGS.timeout}s"
            except json.JSONDecodeError:
                last = "unparseable CLI output"
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"claude CLI failed: {last}")


def flatten(messages) -> str:
    out = []
    for m in messages or []:
        c = m.get("content", "")
        if isinstance(c, list):
            c = "\n".join(b.get("text", "") for b in c
                          if isinstance(b, dict) and b.get("type") == "text")
        role = m.get("role", "user")
        out.append(c if role == "user" else f"[{role}]\n{c}")
    return "\n\n".join(x for x in out if x)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):     # keep the console readable
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._send(200, {"object": "list", "data": [
                {"id": ARGS.model, "object": "model", "owned_by": "anthropic"}]})
        else:
            self._send(200, {"status": "ok", **_STATS})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": {"message": "bad JSON"}})
        prompt = flatten(req.get("messages"))
        model = ARGS.model
        _STATS["calls"] += 1
        try:
            text = call_claude(prompt, model)
        except Exception as e:
            _STATS["errors"] += 1
            return self._send(500, {"error": {"message": str(e)[:300]}})
        self._send(200, {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.get("model", model),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            # SkyDiscover reads usage for its cost telemetry; the CLI does not
            # report per-call tokens, so these are zeros rather than guesses.
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8117)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=600)
    ARGS = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    print(f"claude-openai proxy on http://127.0.0.1:{ARGS.port}/v1  model={ARGS.model}",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
