"""L-Script CLI — Spec → L-Script → Tests → Verdict."""

from __future__ import annotations

import argparse
import sys

from executor import run_sandboxed
from lparser import lscript_to_python
from oracle import generate_tests, run_tests
from translator import translate_to_lscript


def _truncate(s, n: int = 60) -> str:
    s = repr(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lscript",
        description="L-Script: an LLM-native symbolic language MVP",
    )
    parser.add_argument("spec", nargs="?", help="natural-language spec for function f")
    parser.add_argument("--debug", action="store_true", help="show translated Python")
    parser.add_argument("--model", default=None, help="override Gemini model id")
    args = parser.parse_args(argv)

    spec = args.spec or input("Spec> ").strip()
    if not spec:
        print("error: empty spec", file=sys.stderr)
        return 2

    model_kw = {"model": args.model} if args.model else {}

    print("→ Translating spec to L-Script…", file=sys.stderr)
    tres = translate_to_lscript(spec, **model_kw)
    lscript_src = tres.text
    print("\nL-Script:\n  " + lscript_src.replace("\n", "\n  "))
    print(f"\n[{len(lscript_src)} chars, {tres.output_tokens} out tokens, {tres.latency_s:.2f}s]")

    py_src = lscript_to_python(lscript_src)
    if args.debug:
        print("\n--- Python (debug) ---\n" + py_src + "----------------------\n")

    print("→ Generating Oracle tests…", file=sys.stderr)
    cases, _ = generate_tests(spec, **model_kw)

    fn = run_sandboxed(py_src, fn_name="f")
    results = run_tests(fn, cases)

    print("\nTests:")
    passed = 0
    for r in results:
        mark = "✓" if r.passed else "✗"
        line = f"  {mark} {r.case.name}: f({', '.join(_truncate(a) for a in r.case.args)})"
        if r.error:
            line += f"  → ERROR {r.error}"
        elif not r.passed:
            line += f"  → got {_truncate(r.actual)}, expected {_truncate(r.case.expected)}"
        print(line)
        passed += int(r.passed)

    total = len(results)
    verdict = "SUCCESS" if passed == total else "FAIL"
    print(f"\nVerdict: {verdict} ({passed}/{total})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
