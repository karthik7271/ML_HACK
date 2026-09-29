"""Free-first LLM access with automatic fallback.

Providers are tried in DADI_LLM_ORDER (default: groq, gemini, openrouter,
ollama, custom). A provider is used only if its key is set (Ollama needs no
key, just a running local server). A provider that errors or rate-limits is
benched for a minute so live calls fall straight through to the next one.

All providers speak the OpenAI chat-completions API.

Check what works on this machine:  uv run python -m dadi.llm
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import httpx
from openai import AsyncOpenAI

BENCH_SECONDS = 60


@dataclass
class Provider:
    name: str
    base_url: str
    model: str
    key_env: str | None  # None = no key needed (local)
    extra: dict = field(default_factory=dict)


def presets() -> dict[str, Provider]:
    env = os.getenv
    return {
        "groq": Provider("groq", "https://api.groq.com/openai/v1",
                         env("GROQ_MODEL", "openai/gpt-oss-20b"), "GROQ_API_KEY",
                         {"reasoning_effort": "low"}),
        "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/",
                           env("GEMINI_MODEL", "gemini-3.1-flash-lite"), "GEMINI_API_KEY"),
        "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1",
                               env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"), "OPENROUTER_API_KEY"),
        "ollama": Provider("ollama", env("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                           env("OLLAMA_MODEL", "qwen2.5:3b"), None),
        "custom": Provider("custom", env("DADI_LLM_BASE_URL", ""), env("DADI_LLM_MODEL", ""), "DADI_LLM_API_KEY"),
    }


def _ollama_has(base_url: str, model: str) -> bool:
    """True if a local Ollama server is up and has `model` pulled."""
    try:
        tags = httpx.get(base_url.replace("/v1", "/api/tags"), timeout=0.5).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return False
    names = {t.get("name") for t in tags} | {t.get("model") for t in tags}
    return model in names or f"{model}:latest" in names


class LLM:
    def __init__(self, timeout: float | None = None):
        self.timeout = timeout or float(os.getenv("DADI_LLM_TIMEOUT", "6"))
        order = os.getenv("DADI_LLM_ORDER", "groq,gemini,openrouter,ollama,custom").split(",")
        all_presets = presets()
        self.providers: list[tuple[Provider, AsyncOpenAI]] = []
        for name in (n.strip() for n in order):
            p = all_presets.get(name)
            if not p:
                continue
            if p.key_env is None:
                if not _ollama_has(p.base_url, p.model):
                    continue
                key = "ollama"
            else:
                key = os.getenv(p.key_env)
                if not key or not p.base_url or not p.model:
                    continue
            self.providers.append((p, AsyncOpenAI(api_key=key, base_url=p.base_url, timeout=self.timeout, max_retries=0)))
        self._benched_until: dict[str, float] = {}

    @property
    def available(self) -> bool:
        return bool(self.providers)

    @property
    def description(self) -> str:
        return " → ".join(f"{p.name}:{p.model}" for p, _ in self.providers) or "none"

    async def complete(self, messages: list[dict], max_tokens: int = 120, temperature: float = 0.9) -> tuple[str, str]:
        """Returns (text, provider name). Raises RuntimeError if every provider fails."""
        errors = []
        now = time.monotonic()
        for p, client in self.providers:
            if self._benched_until.get(p.name, 0) > now:
                continue
            try:
                resp = await client.chat.completions.create(
                    model=p.model, messages=messages, max_tokens=max_tokens, temperature=temperature,
                    extra_body=p.extra or None)
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    return text, p.name
                errors.append(f"{p.name}: empty reply")
            except Exception as e:  # rate limit, timeout, bad model name, ...
                errors.append(f"{p.name}: {type(e).__name__}: {str(e)[:120]}")
                self._benched_until[p.name] = time.monotonic() + BENCH_SECONDS
        raise RuntimeError("; ".join(errors) or "no LLM provider configured")


async def _check() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    llm = LLM(timeout=20)
    print(f"configured: {llm.description}")
    for p, client in llm.providers:
        t = time.monotonic()
        try:
            resp = await client.chat.completions.create(
                model=p.model, max_tokens=60, extra_body=p.extra or None,
                messages=[{"role": "user", "content": "Say namaste like a sweet Indian grandmother, in one short Hinglish sentence."}])
            print(f"  ✓ {p.name:10} {p.model:45} {time.monotonic() - t:5.2f}s  {resp.choices[0].message.content!r}")
        except Exception as e:
            print(f"  ✗ {p.name:10} {p.model:45} {type(e).__name__}: {str(e)[:160]}")
    if not llm.providers:
        print("No provider available. Set GROQ_API_KEY (free at console.groq.com) in .env,\n"
              "or run a local model:  ollama pull qwen2.5:3b")


if __name__ == "__main__":
    asyncio.run(_check())
