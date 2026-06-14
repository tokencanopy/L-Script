"""Translator: English spec → L-Script (or plain Python) via Gemini."""

from __future__ import annotations

import re

from grammar import GRAMMAR_SPEC
from llm import DEFAULT_MODEL, LLMResult, call


_LSCRIPT_SYSTEM = f"""\
You are a code compiler for L-Script v0.1, a high-density symbolic language.

{GRAMMAR_SPEC}

CRITICAL: Output token efficiency is paramount. Use single-letter identifiers.
No prose, no explanation, no code fences, no markdown. Emit ONLY raw L-Script
characters for a single function named `f`. The function MUST start with ℱf⇥
and be terminated by ⚀.
"""

_PYTHON_SYSTEM = """\
You are a code compiler. Given an English spec, emit ONE Python function named
`f` that satisfies it.

CONSTRAINTS:
- Use only stdlib builtins (sorted, len, range, sum, max, min, set, list, dict,
  enumerate, zip, map, filter, any, all, abs, str, int, bool, reversed, round).
- NO imports, NO type hints, NO docstrings, NO comments, NO print statements.
- Function MUST be named exactly `f`.
- Use single-letter identifiers where possible (L, S, X, Y, A, B, T, n, i, j).
- Output ONLY the raw Python source. No markdown fences, no prose.
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def translate_to_lscript(
    spec: str,
    *,
    client=None,
    model: str = DEFAULT_MODEL,
) -> LLMResult:
    """English spec → L-Script source. Returns full LLMResult for metrics."""
    res = call(
        system=_LSCRIPT_SYSTEM,
        user=f"Spec: {spec}\n\nEmit L-Script only.",
        model=model,
        client=client,
        max_tokens=1024,
    )
    res.text = _strip_fences(res.text)
    return res


def translate_to_python(
    spec: str,
    *,
    client=None,
    model: str = DEFAULT_MODEL,
) -> LLMResult:
    """English spec → plain Python source. Same prompt scaffold as L-Script."""
    res = call(
        system=_PYTHON_SYSTEM,
        user=f"Spec: {spec}\n\nEmit Python only.",
        model=model,
        client=client,
        max_tokens=1024,
    )
    res.text = _strip_fences(res.text)
    return res
