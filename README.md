# L-Script

An experimental **LLM-native symbolic language**. L-Script tests a simple
hypothesis: *if you give an LLM a denser, more compact language to write code in,
does it become cheaper and just as correct as plain Python?*

The pipeline is:

```
English spec  ──▶  L-Script  ──▶  Python  ──▶  sandbox  ──▶  Oracle tests  ──▶  verdict
              (LLM)          (parser)      (exec)        (LLM-generated)
```

An LLM (Gemini) translates a natural-language spec into L-Script — a high-density
notation built from symbols like `ℱ ⇥ § ¿ ⧖ ⧉ ⚀`. A hand-written parser compiles
that into ordinary Python, which runs in a restricted sandbox and is checked
against edge-case unit tests that a second LLM call (the "Oracle") generates from
the same spec.

> **Research status.** This is an active research artifact, not a product. Early
> benchmark results suggest the core hypothesis does **not** hold as stated — the
> symbolic density saves *characters* but not *tokens* (rare Unicode glyphs
> tokenize poorly), while correctness drops. See [Findings](#findings) below; the
> repo exists to study *why*.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env          # then add your Gemini API key
python lscript.py "sum of even integers below n"
```

Set your key in `.env`:

```
GEMINI_API_KEY=your-gemini-api-key
# Optional: override the model (default: gemini-2.5-flash)
# LSCRIPT_MODEL=gemini-2.5-pro
```

Example run:

```
$ python lscript.py "reverse a string"

L-Script:
  ℱf⇥S ⧉S[::-1] ⚀

→ Generating Oracle tests…

Tests:
  ✓ empty: f('')
  ✓ single: f('a')
  ...
Verdict: SUCCESS (5/5)
```

Use `--debug` to print the Python that L-Script compiles to, and `--model` to
override the model for a single run.

## How it works

| File | Role |
|------|------|
| [`lscript.py`](lscript.py) | CLI entry point: spec → L-Script → tests → verdict |
| [`grammar.py`](grammar.py) | The L-Script v0.2 grammar — symbol table + the spec handed to the LLM |
| [`translator.py`](translator.py) | English spec → L-Script (or plain Python) via the LLM |
| [`lparser.py`](lparser.py) | Parses L-Script symbols into executable Python source |
| [`executor.py`](executor.py) | Restricted `exec` sandbox (allowlisted builtins, AST audit, no imports) |
| [`oracle.py`](oracle.py) | LLM-generated edge-case unit tests + test runner |
| [`llm.py`](llm.py) | Thin Gemini client wrapper (tokens, latency, token counting) |
| [`benchmark/`](benchmark/) | Harness comparing the L-Script and plain-Python pipelines |

### The L-Script grammar (v0.2)

A single function `f`, built from block openers each closed by `⚀`:

```
ℱf⇥n §T=0 ⧖i∈range(n)⇥ ¿i%2==0⇥ §T=T+i ⚀ ⚀ ⧉T ⚀
```

| Symbol | Meaning | | Symbol | Meaning |
|--------|---------|---|--------|---------|
| `ℱ` | function def | | `⧖` | for / while loop |
| `⇥` | arg / block opener | | `∈` | for-loop iterable separator |
| `§` | assignment | | `⧉` | return |
| `¿` `⁇` `¡` | if / elif / else | | `⊗` `⊙` | break / continue |
| `⚀` | end-of-block | | `⍃` | list-op prefix (`⍃sort`, `⍃len`, …) |

The full machine-readable grammar lives in [`grammar.py`](grammar.py).

## Benchmark

The harness runs each problem through both pipelines (`python` and `lscript`),
logging per-sample token cost, latency, correctness against held-out gold tests,
and failure modes to a CSV for analysis.

```bash
# Dry run — print the plan without calling the LLM
python benchmark/harness.py --dry-run

# Full run: all problems, 5 samples each, both pipelines
python benchmark/harness.py --samples 5 --out benchmark/results.csv

# Useful flags
python benchmark/harness.py --limit 3 --debug-dir benchmark/debug --with-oracle
```

Results are written to `benchmark/results.csv` (gitignored). The v0.1 baseline
results are checked in at [`benchmark/results_v01.csv`](benchmark/results_v01.csv).

## Findings

From the v0.1 baseline (10 problems, 1 sample, `gemini-2.5-flash`):

- **Correctness regresses.** Plain Python: 10/10 pass@1. L-Script: 6/10.
- **No token savings.** L-Script's source has far fewer *characters* but roughly
  the same number of *tokens* — its rare Unicode glyphs cost ~1 token each, while
  Python keywords are single tokens covering many characters.
- **Large in-context grammar tax.** The model must be taught the grammar on every
  call (~700 tokens), so total token cost runs 3–4× higher than plain Python.

The working interpretation: L-Script optimizes *character* count, but LLMs are
priced and bottlenecked in *tokens*, and its alphabet of rare glyphs tokenizes
poorly — so it spends more tokens to say less, in a language the model was never
trained to write. The constructive takeaway is **token-awareness**: a useful
LLM-native DSL should be built from sequences that are already cheap in the
target tokenizer.

## Requirements

- Python 3.10+
- A Gemini API key (`GEMINI_API_KEY`)
- `google-genai`, `python-dotenv` (see [`requirements.txt`](requirements.txt))
