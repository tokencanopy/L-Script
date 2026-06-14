"""Oracle: English spec → 5 edge-case unit tests via Gemini."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from llm import DEFAULT_MODEL, LLMResult, call

_ORACLE_SYSTEM = """\
You are a unit-test designer. Given an English spec for a function named `f`,
produce exactly 5 edge-case test cases as a JSON array. Each item is an object:

  {"name": "<short label>", "args": [<positional args>], "expected": <value>}

RULES:
- args is an ALWAYS-A-LIST of positional arguments to call f(*args).
- expected is a JSON-serializable value f should return.
- Cover edge cases: empty input, single element, duplicates, large input,
  off-by-one, negative numbers, sorting stability, unicode, etc — whichever
  apply to the spec.
- For sorting/dedup tasks, the test must be deterministic (no ambiguous order).
- Output ONLY the JSON array. No prose, no markdown fences.
"""


@dataclass
class TestCase:
    name: str
    args: list
    expected: object


@dataclass
class TestResult:
    case: TestCase
    passed: bool
    actual: object | None
    error: str | None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def generate_tests(
    spec: str,
    *,
    client=None,
    model: str = DEFAULT_MODEL,
) -> tuple[list[TestCase], LLMResult]:
    """Returns (cases, full LLM result for metrics)."""
    res = call(
        system=_ORACLE_SYSTEM,
        user=f"Spec: {spec}",
        model=model,
        client=client,
        max_tokens=2048,
    )
    text = _strip_fences(res.text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"oracle did not return a JSON array: {text[:200]}")
    cases = [TestCase(name=d["name"], args=d["args"], expected=d["expected"]) for d in data]
    return cases, res


def run_tests(fn, cases: list[TestCase]) -> list[TestResult]:
    results: list[TestResult] = []
    for case in cases:
        try:
            actual = fn(*case.args)
            passed = actual == case.expected
            results.append(TestResult(case=case, passed=passed, actual=actual, error=None))
        except Exception as e:
            results.append(
                TestResult(
                    case=case,
                    passed=False,
                    actual=None,
                    error=f"{type(e).__name__}: {e}",
                )
            )
    return results
