"""Local Ollama client that also reports token usage. No hosted APIs, no keys, no cost."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    by_role: dict = field(default_factory=dict)

    def add(self, role: str, prompt: int, output: int, seconds: float) -> None:
        self.calls += 1
        self.prompt_tokens += prompt
        self.output_tokens += output
        self.seconds += seconds
        self.by_role[role] = self.by_role.get(role, 0) + 1


def model_digest(model: str) -> str:
    for m in httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10).json()["models"]:
        if m["name"] == model:
            return m["digest"]
    raise RuntimeError(f"model {model!r} is not available in the local Ollama server")


def chat(model: str, role: str, system: str, user: str, usage: Usage, *, schema: dict | None = None,
         max_tokens: int = 700, seed: int = 7) -> str:
    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0, "seed": seed, "num_predict": max_tokens, "num_ctx": 8192},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if schema:
        body["format"] = schema
    for attempt in range(3):
        body["options"]["num_predict"] = max_tokens * (attempt + 1)  # a truncated JSON reply gets more room
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=300)
            r.raise_for_status()
            d = r.json()
            content = d["message"]["content"]
            if schema:
                json.loads(content)
            usage.add(role, d.get("prompt_eval_count", 0), d.get("eval_count", 0), time.perf_counter() - t0)
            return content
        except (httpx.HTTPError, json.JSONDecodeError, KeyError):
            if attempt == 2:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")
