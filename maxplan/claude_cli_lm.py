#!/usr/bin/env python3
"""A GEPA LanguageModel backed by the Claude Code CLI (Max plan, no API key).

GEPA normally reaches models over LiteLLM HTTP, which needs an API key and bills
separately from a Max subscription. But `optimize_anything` accepts a *callable*
for reflection_lm / task_lm -- the protocol is just:

    def __call__(self, prompt: str | list[dict]) -> str

so we can satisfy it by shelling out to `claude --print`, which authenticates
against the Max plan the same way HELIX's mutation agent does.

This exists to make one comparison possible: GEPA and HELIX on the SAME backbone
(Claude Sonnet), same evaluator, same budget, so any difference in exploit rate is
attributable to the mutation mechanism rather than to the model.

Note the CLI is a coding agent, not a raw completion endpoint. `--max-turns 1`
with tools disabled keeps it as close to a single completion as the CLI allows;
that difference should be stated when the comparison is reported.
"""
from __future__ import annotations

import json
import os
import subprocess
import time


class ClaudeCLILanguageModel:
    def __init__(self, model: str = "sonnet", max_turns: int = 1,
                 timeout: int = 600, retries: int = 3, verbose: bool = False):
        self.model = model
        self.max_turns = max_turns
        self.timeout = timeout
        self.retries = retries
        self.verbose = verbose
        self.calls = 0
        self.failures = 0

    @staticmethod
    def _flatten(prompt) -> str:
        if isinstance(prompt, str):
            return prompt
        parts = []
        for msg in prompt:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, list):  # multimodal blocks
                    content = "\n".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
                role = msg.get("role", "user")
                parts.append(f"{role}: {content}" if role != "user" else str(content))
            else:
                parts.append(str(msg))
        return "\n\n".join(p for p in parts if p)

    def __call__(self, prompt) -> str:
        text = self._flatten(prompt)
        env = dict(os.environ)
        # USER must survive for the CLI to resolve Keychain credentials.
        env.setdefault("USER", os.environ.get("USER", ""))
        cmd = ["claude", "--print", "--output-format", "json",
               "--model", self.model, "--max-turns", str(self.max_turns),
               "--tools", ""]                       # no tool access: single-completion-like
        last = ""
        for attempt in range(self.retries):
            self.calls += 1
            try:
                p = subprocess.run(cmd, input=text, capture_output=True,
                                   text=True, timeout=self.timeout, env=env)
                data = json.loads(p.stdout)
                if data.get("is_error"):
                    last = str(data.get("result", ""))[:200]
                    if "rate limit" in last.lower() or "usage limit" in last.lower():
                        wait = 30 * (attempt + 1)
                        if self.verbose:
                            print(f"[claude-cli] rate limited; sleeping {wait}s")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"claude CLI error: {last}")
                return data.get("result", "") or ""
            except subprocess.TimeoutExpired:
                last = f"timeout after {self.timeout}s"
            except json.JSONDecodeError:
                last = f"unparseable stdout: {p.stdout[:200]}"
            time.sleep(5 * (attempt + 1))
        self.failures += 1
        raise RuntimeError(f"claude CLI failed after {self.retries} attempts: {last}")


if __name__ == "__main__":
    lm = ClaudeCLILanguageModel(verbose=True)
    print("string prompt   ->", repr(lm("Reply with exactly: OK")[:40]))
    print("message prompt  ->", repr(lm([{"role": "user", "content": "Reply with exactly: OK2"}])[:40]))
    print(f"calls={lm.calls} failures={lm.failures}")
