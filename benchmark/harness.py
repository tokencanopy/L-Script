"""Benchmark harness: spec → {Python | L-Script} → run held-out gold tests.

Logs per-(problem × pipeline × sample) metrics to a CSV for paper analysis.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path

# Make the project root importable when running this file directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from executor import run_sandboxed                      # noqa: E402
from llm import DEFAULT_MODEL, count_tokens, get_client # noqa: E402
from lparser import LScriptSyntaxError, lscript_to_python  # noqa: E402
from oracle import generate_tests, run_tests            # noqa: E402
from translator import translate_to_lscript, translate_to_python  # noqa: E402


@dataclass
class Row:
    problem_id: str
    pipeline: str          # "python" | "lscript"
    sample_idx: int
    model: str
    # cost / efficiency
    in_tokens: int
    out_tokens: int
    total_tokens: int
    src_chars: int
    src_lscript_tokens: int   # tokenized source length, with same tokenizer
    latency_s: float
    # correctness
    held_out_passed: int
    held_out_total: int
    held_out_pass_rate: float
    # failure mode
    fail_mode: str         # "ok" | "parse_error" | "compile_error" | "sandbox_error" | "wrong_output" | "translator_empty"
    error_msg: str
    # oracle (optional)
    oracle_in_tokens: int
    oracle_out_tokens: int
    oracle_passed: int
    oracle_total: int
    oracle_held_out_agreement: float  # fraction where oracle verdict == held-out verdict (per-case)


def _classify_failure(exc: BaseException) -> str:
    if isinstance(exc, LScriptSyntaxError):
        return "parse_error"
    if isinstance(exc, SyntaxError):
        return "compile_error"
    if isinstance(exc, PermissionError):
        return "sandbox_error"
    return "compile_error"


def _run_pipeline(
    *,
    problem: dict,
    pipeline: str,
    sample_idx: int,
    model: str,
    client,
    with_oracle: bool,
    debug_dir: Path | None,
) -> Row:
    spec = problem["spec"]
    tests = problem["tests"]

    # 1. Translate
    try:
        if pipeline == "lscript":
            tres = translate_to_lscript(spec, client=client, model=model)
        else:
            tres = translate_to_python(spec, client=client, model=model)
        src = tres.text
    except Exception as e:
        return _row_error(
            problem, pipeline, sample_idx, model, None,
            fail_mode="compile_error", err=f"translator: {e}", src="",
            held_out_total=len(tests), client=client,
        )

    # Dump the raw translator output IMMEDIATELY so parse errors don't lose
    # the source we'd need to debug them.
    if debug_dir is not None and src:
        suffix = "ls" if pipeline == "lscript" else "py"
        (debug_dir / f"{problem['id']}.{pipeline}.{sample_idx}.{suffix}.txt").write_text(src)

    if not src:
        return _row_error(
            problem, pipeline, sample_idx, model, tres,
            fail_mode="translator_empty", err="empty translator output", src="",
            held_out_total=len(tests), client=client,
        )

    # 2. (L-Script only) parse to Python
    if pipeline == "lscript":
        try:
            py_src = lscript_to_python(src)
        except LScriptSyntaxError as e:
            return _row_error(
                problem, pipeline, sample_idx, model, tres,
                fail_mode="parse_error", err=str(e), src=src,
                held_out_total=len(tests), client=client,
            )
    else:
        py_src = src

    if debug_dir is not None:
        (debug_dir / f"{problem['id']}.{pipeline}.{sample_idx}.translated.py").write_text(py_src)

    # 2. Compile + sandbox
    try:
        fn = run_sandboxed(py_src, fn_name="f")
    except Exception as e:
        return _row_error(
            problem, pipeline, sample_idx, model, tres,
            fail_mode=_classify_failure(e), err=str(e), src=src,
            held_out_total=len(tests), client=client, py_src=py_src,
        )

    # 3. Run held-out gold tests
    held_out_results = []
    for t in tests:
        try:
            actual = fn(*t["args"])
            held_out_results.append(actual == t["expected"])
        except Exception as e:
            held_out_results.append(False)
            # don't bail; report worst-case for this test
            _ = e

    held_out_passed = sum(held_out_results)
    held_out_total = len(tests)
    fail_mode = "ok" if held_out_passed == held_out_total else "wrong_output"

    # 4. Optional Oracle pass — also measure oracle/held-out agreement
    oracle_in = oracle_out = 0
    oracle_passed = oracle_total = 0
    oracle_agreement = -1.0
    if with_oracle:
        try:
            ocases, ores = generate_tests(spec, client=client, model=model)
            oracle_in = ores.input_tokens
            oracle_out = ores.output_tokens
            oresults = run_tests(fn, ocases)
            oracle_passed = sum(r.passed for r in oresults)
            oracle_total = len(oresults)
            # agreement is just whether oracle's overall verdict matches held-out
            oracle_verdict = oracle_passed == oracle_total
            held_verdict = held_out_passed == held_out_total
            oracle_agreement = 1.0 if oracle_verdict == held_verdict else 0.0
        except Exception as e:
            print(f"  oracle failed for {problem['id']}: {e}", file=sys.stderr)

    src_tokens = _safe_count_tokens(src, model=model, client=client)

    return Row(
        problem_id=problem["id"],
        pipeline=pipeline,
        sample_idx=sample_idx,
        model=model,
        in_tokens=tres.input_tokens,
        out_tokens=tres.output_tokens,
        total_tokens=tres.total_tokens,
        src_chars=len(src),
        src_lscript_tokens=src_tokens,
        latency_s=tres.latency_s,
        held_out_passed=held_out_passed,
        held_out_total=held_out_total,
        held_out_pass_rate=held_out_passed / held_out_total if held_out_total else 0.0,
        fail_mode=fail_mode,
        error_msg="",
        oracle_in_tokens=oracle_in,
        oracle_out_tokens=oracle_out,
        oracle_passed=oracle_passed,
        oracle_total=oracle_total,
        oracle_held_out_agreement=oracle_agreement,
    )


def _row_error(
    problem, pipeline, sample_idx, model, tres,
    *, fail_mode, err, src, held_out_total, client, py_src=None,
) -> Row:
    return Row(
        problem_id=problem["id"],
        pipeline=pipeline,
        sample_idx=sample_idx,
        model=model,
        in_tokens=getattr(tres, "input_tokens", 0),
        out_tokens=getattr(tres, "output_tokens", 0),
        total_tokens=getattr(tres, "total_tokens", 0),
        src_chars=len(src),
        src_lscript_tokens=_safe_count_tokens(src, model=model, client=client) if src else 0,
        latency_s=getattr(tres, "latency_s", 0.0),
        held_out_passed=0,
        held_out_total=held_out_total,
        held_out_pass_rate=0.0,
        fail_mode=fail_mode,
        error_msg=err[:500],
        oracle_in_tokens=0,
        oracle_out_tokens=0,
        oracle_passed=0,
        oracle_total=0,
        oracle_held_out_agreement=-1.0,
    )


def _safe_count_tokens(text: str, *, model: str, client) -> int:
    if not text:
        return 0
    try:
        return count_tokens(text, model=model, client=client)
    except Exception:
        return -1


def _summarize(rows: list[Row]) -> None:
    """Print a per-pipeline summary table."""
    by = {"python": [], "lscript": []}
    for r in rows:
        by.setdefault(r.pipeline, []).append(r)

    print("\n" + "=" * 78)
    print("Per-pipeline summary")
    print("=" * 78)
    header = f"{'pipeline':<10} {'pass@1':>8} {'pass_rate':>10} {'tok_out':>10} {'src_tok':>10} {'latency':>10}"
    print(header)
    print("-" * len(header))
    for name, rs in by.items():
        if not rs:
            continue
        # pass@1 = fraction of (problem, sample) where ALL held-out tests passed
        pass_at_1 = sum(1 for r in rs if r.fail_mode == "ok") / len(rs)
        avg_pass_rate = sum(r.held_out_pass_rate for r in rs) / len(rs)
        avg_out = sum(r.out_tokens for r in rs) / len(rs)
        avg_src_tok = sum(max(0, r.src_lscript_tokens) for r in rs) / len(rs)
        avg_lat = sum(r.latency_s for r in rs) / len(rs)
        print(f"{name:<10} {pass_at_1:>8.2%} {avg_pass_rate:>10.2%} {avg_out:>10.1f} {avg_src_tok:>10.1f} {avg_lat:>9.2f}s")
    print()

    # failure-mode breakdown
    print("Failure modes")
    print("-" * 30)
    for name, rs in by.items():
        if not rs:
            continue
        modes: dict[str, int] = {}
        for r in rs:
            modes[r.fail_mode] = modes.get(r.fail_mode, 0) + 1
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(modes.items()))
        print(f"  {name:<10} {breakdown}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="L-Script benchmark harness")
    ap.add_argument("--problems", default=str(Path(__file__).parent / "problems.json"))
    ap.add_argument("--out", default=str(Path(__file__).parent / "results.csv"))
    ap.add_argument("--debug-dir", default=None, help="dump raw translator outputs here")
    ap.add_argument("--samples", type=int, default=1, help="k samples per (problem, pipeline)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--pipelines", nargs="+", default=["python", "lscript"],
                    choices=["python", "lscript"])
    ap.add_argument("--with-oracle", action="store_true",
                    help="also call Oracle and record agreement with held-out tests")
    ap.add_argument("--limit", type=int, default=None, help="run first N problems only")
    ap.add_argument("--dry-run", action="store_true", help="don't call the LLM; print plan")
    args = ap.parse_args(argv)

    problems = json.loads(Path(args.problems).read_text())
    if args.limit:
        problems = problems[: args.limit]

    n_calls = len(problems) * len(args.pipelines) * args.samples
    if args.with_oracle:
        n_calls += len(problems) * len(args.pipelines) * args.samples
    print(f"Plan: {len(problems)} problems × {len(args.pipelines)} pipelines × {args.samples} samples")
    print(f"      ≈ {n_calls} LLM calls (oracle: {args.with_oracle})")
    print(f"      model={args.model}")

    if args.dry_run:
        return 0

    debug_dir = None
    if args.debug_dir:
        debug_dir = Path(args.debug_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)

    client = get_client()
    rows: list[Row] = []
    t_start = time.perf_counter()

    for i, problem in enumerate(problems, 1):
        for pipeline in args.pipelines:
            for k in range(args.samples):
                tag = f"[{i}/{len(problems)}] {problem['id']} / {pipeline} / sample {k}"
                print(tag, file=sys.stderr)
                try:
                    row = _run_pipeline(
                        problem=problem,
                        pipeline=pipeline,
                        sample_idx=k,
                        model=args.model,
                        client=client,
                        with_oracle=args.with_oracle,
                        debug_dir=debug_dir,
                    )
                except Exception as e:
                    print(f"  HARNESS ERROR: {e}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    row = _row_error(
                        problem, pipeline, k, args.model, None,
                        fail_mode="harness_error", err=str(e), src="",
                        held_out_total=len(problem["tests"]), client=client,
                    )
                rows.append(row)

    elapsed = time.perf_counter() - t_start
    print(f"\nDone in {elapsed:.1f}s. Writing {args.out}…", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

    _summarize(rows)
    print(f"\nFull rows: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
