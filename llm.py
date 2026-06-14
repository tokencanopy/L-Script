"""Thin Gemini client wrapper used by translator + oracle + harness."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Auto-load .env from the project root if python-dotenv is available.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

DEFAULT_MODEL = os.environ.get("LSCRIPT_MODEL", "gemini-2.5-flash")


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str
    latency_s: float


def get_client(api_key: str | None = None):
    from google import genai
    return genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))


def call(
    *,
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    client=None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
    thinking_budget: int | None = 0,
) -> LLMResult:
    """One-shot Gemini call. Returns text + token usage + latency.

    thinking_budget: 0 disables 2.5-series thinking (default — code emission
    doesn't need it and thinking tokens compete with the output budget).
    Pass None to use the model default, or a positive int to set a budget.
    """
    import time
    from google.genai import types

    client = client or get_client()
    cfg_kwargs = {
        "system_instruction": system,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if thinking_budget is not None:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    cfg = types.GenerateContentConfig(**cfg_kwargs)

    t0 = time.perf_counter()
    resp = client.models.generate_content(model=model, contents=user, config=cfg)
    latency = time.perf_counter() - t0

    usage = getattr(resp, "usage_metadata", None)
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    total = getattr(usage, "total_token_count", in_tok + out_tok) or (in_tok + out_tok)

    return LLMResult(
        text=resp.text or "",
        input_tokens=in_tok,
        output_tokens=out_tok,
        total_tokens=total,
        model=model,
        latency_s=latency,
    )


def count_tokens(text: str, *, model: str = DEFAULT_MODEL, client=None) -> int:
    """Tokenize a string with Gemini's tokenizer (for offline density measurements)."""
    client = client or get_client()
    resp = client.models.count_tokens(model=model, contents=text)
    return int(resp.total_tokens)
