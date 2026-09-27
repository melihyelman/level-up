"""GLM-5.3-Flash through the organisers' OpenAI-compatible gateway, with usage accounting."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI

from stage2.asama2.baseguard.core import config

load_dotenv(config.ROOT / ".env")

BASE_URL = os.getenv("GLM_BASE_URL", "https://berriailitellm-databasev1826rc3-production-d691.up.railway.app/v1")
MODEL = os.getenv("GLM_MODEL", "glm-5.3-flash")
USAGE_LOG = config.CACHE_DIR / "llm_usage.jsonl"

# gateway allows 4 concurrent requests per team; keep a margin for the UI
_slots = threading.BoundedSemaphore(int(os.getenv("GLM_MAX_CONCURRENCY", "3")))


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    seconds: float = 0.0
    log: list = field(default_factory=list)

    def add(self, u, dt: float):
        self.calls += 1
        self.seconds += dt
        if u:
            self.prompt_tokens += u.prompt_tokens or 0
            self.completion_tokens += u.completion_tokens or 0
            det = getattr(u, "completion_tokens_details", None)
            self.reasoning_tokens += (getattr(det, "reasoning_tokens", 0) or 0) if det else 0

    def as_dict(self):
        return dict(calls=self.calls, prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens,
                    reasoning_tokens=self.reasoning_tokens, seconds=round(self.seconds, 1))


_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    key = os.getenv("GLM_API_KEY")
    if not key:
        raise LLMUnavailable("GLM_API_KEY tanımlı değil (.env dosyasına ekleyin)")
    if _client is None:
        _client = OpenAI(base_url=BASE_URL, api_key=key, max_retries=5, timeout=180)
    return _client


def available() -> bool:
    return bool(os.getenv("GLM_API_KEY"))


def chat(messages: list, usage: Usage, tools: list | None = None, effort: str = "low", **kw):
    """One chat completion. Never pass max_tokens small: reasoning tokens count against it."""
    args = dict(model=MODEL, messages=messages, reasoning_effort=effort, **kw)
    if tools:
        args["tools"] = tools
    t = time.time()
    with _slots:
        resp = client().chat.completions.create(**args)
    dt = time.time() - t
    usage.add(resp.usage, dt)
    try:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG, "a") as f:
            f.write(json.dumps(dict(ts=time.time(), dt=round(dt, 2),
                                    usage=resp.usage.model_dump() if resp.usage else None)) + "\n")
    except OSError:
        pass
    return resp


def budget_info() -> dict | None:
    """Remaining team budget from the gateway (spend / max_budget)."""
    import urllib.request
    key = os.getenv("GLM_API_KEY")
    if not key:
        return None
    req = urllib.request.Request(BASE_URL.rsplit("/v1", 1)[0] + "/key/info", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            info = json.loads(r.read()).get("info", {})
        return dict(spend=info.get("spend"), max_budget=info.get("max_budget"))
    except Exception:
        return None
