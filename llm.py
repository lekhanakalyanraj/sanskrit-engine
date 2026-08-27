# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""llm.py — provider-agnostic LLM shim.

Every provider here speaks the OpenAI-compatible chat API, so switching between a free
local model and a hosted one is ONE env var — no code change in the agents.

    export LLM_PROVIDER=ollama        # default; free, local. `ollama pull qwen2.5:7b`
    export LLM_PROVIDER=groq          # free tier, fast; needs GROQ_API_KEY
    export LLM_PROVIDER=huggingface   # free tier; needs HF_TOKEN
    export LLM_PROVIDER=openrouter    # free open-model tiers; needs OPENROUTER_API_KEY
    export LLM_PROVIDER=sarvam        # India-made, Indic-trained; needs SARVAM_API_KEY
    export LLM_PROVIDER=claude        # optional paid upgrade; needs ANTHROPIC_API_KEY

Override any preset explicitly:
    export LLM_MODEL=llama-3.1-8b-instant
    export LLM_BASE_URL=...   export LLM_API_KEY=...

Usage:
    from llm import chat
    print(chat("You explain Sanskrit grammar.", "What kāraka role is the instrumental case?"))

Requires:  pip install openai         (structured output also: pip install instructor)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# name -> (base_url, default_model, env var holding the API key, needs a key?)
# NOTE: base URLs / model ids drift — verify against each provider's current docs before deploy.
PRESETS: dict[str, tuple[str, str, str, bool]] = {
    "ollama":      ("http://localhost:11434/v1",     "qwen2.5:7b",                  "",                   False),
    "groq":        ("https://api.groq.com/openai/v1", "llama-3.1-8b-instant",       "GROQ_API_KEY",       True),
    "huggingface": ("https://router.huggingface.co/v1", "Qwen/Qwen2.5-7B-Instruct", "HF_TOKEN",           True),
    "openrouter":  ("https://openrouter.ai/api/v1",   "meta-llama/llama-3.1-8b-instruct", "OPENROUTER_API_KEY", True),
    "sarvam":      ("https://api.sarvam.ai/v1",       "sarvam-m",                    "SARVAM_API_KEY",     True),
    "claude":      ("https://api.anthropic.com/v1/",  "claude-sonnet-5",             "ANTHROPIC_API_KEY",  True),
}


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: str


def load_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider not in PRESETS:
        raise ValueError(f"unknown LLM_PROVIDER={provider!r}; choose one of {list(PRESETS)}")
    base_url, model, key_env, needs_key = PRESETS[provider]

    base_url = os.getenv("LLM_BASE_URL", base_url)
    model = os.getenv("LLM_MODEL", model)
    # explicit LLM_API_KEY wins; else the provider's env var; Ollama accepts any placeholder
    api_key = os.getenv("LLM_API_KEY") or (os.getenv(key_env, "") if key_env else "")
    if needs_key and not api_key:
        raise RuntimeError(f"LLM_PROVIDER={provider} needs an API key in ${key_env} (or $LLM_API_KEY)")
    return LLMConfig(provider, base_url, model, api_key or "not-needed")


_client = None
_config: LLMConfig | None = None


def reset() -> None:
    """Forget the cached client/config so a changed LLM_PROVIDER takes effect (used by the playground)."""
    global _client, _config
    _client = None
    _config = None


def _get_client():
    global _client, _config
    if _client is None:
        from openai import OpenAI
        _config = load_config()
        _client = OpenAI(base_url=_config.base_url, api_key=_config.api_key)
        print(f"[llm] provider={_config.provider} model={_config.model}")
    return _client, _config


def chat(system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 800) -> str:
    """One-shot chat completion → assistant text. Works on every provider above."""
    client, config = _get_client()
    resp = client.chat.completions.create(
        model=config.model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def chat_structured(system: str, user: str, schema, *, temperature: float = 0.0):
    """Return a validated Pydantic object. Uses `instructor` for cross-provider JSON.

    `schema` is a pydantic.BaseModel subclass. This is how the agents (disambiguator,
    verifier, …) return typed output instead of free text — the key hallucination guard.
    """
    import instructor
    client, config = _get_client()
    # JSON mode (not the default TOOLS mode): the model returns a plain JSON object matching the
    # schema, avoiding Ollama's intermittent "multiple tool calls" error and working across providers.
    patched = instructor.from_openai(client, mode=instructor.Mode.JSON)
    return patched.chat.completions.create(
        model=config.model,
        response_model=schema,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
    )


if __name__ == "__main__":
    # Smoke test: `python llm.py`  (start Ollama first, or set LLM_PROVIDER)
    print(chat(
        system="You are a concise Sanskrit tutor. Answer in one sentence.",
        user="In 'bālaḥ hastena annaṃ khādati', what kāraka role does 'hastena' fill?",
    ))
