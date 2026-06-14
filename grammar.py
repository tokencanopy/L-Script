"""L-Script v0.2 grammar — symbol table and machine-readable spec for the LLM."""

SYMBOLS = {
    "FUNC":    "ℱ",   # function definition
    "ARGS":    "⇥",   # arg / block-opener delimiter
    "ASSIGN":  "§",   # variable assignment
    "COND":    "¿",   # if
    "ELIF":    "⁇",   # elif (NEW in v0.2 — multi-branch without nesting)
    "ELSE":    "¡",   # else
    "LOOP":    "⧖",   # for (with ∈) OR while (without ∈)
    "IN":      "∈",   # for-loop iterable separator
    "RETURN":  "⧉",   # return
    "BREAK":   "⊗",   # break
    "CONT":    "⊙",   # continue
    "END":     "⚀",   # end-of-block
    "LIST":    "⍃",   # list-op prefix
}

# ⍃<name>(...) translations. Values that are bare names refer to a
# Python callable; values starting with "lambda" get wrapped in parens.
# Helpers prefixed with `_` are injected into the executor's globals.
LIST_OPS = {
    # core sequence ops — POLYMORPHIC over str/list when it makes sense
    "sort":    "_sort",     # str→str sorted chars; else sorted(list)
    "rsort":   "_rsort",    # reverse sort
    "unique":  "_uniq",     # de-dup, preserves order; str→str, list→list
    "rev":     "_rev",      # str→str reversed; list→list reversed
    # aggregations — language-agnostic
    "len":     "len",
    "max":     "max",
    "min":     "min",
    "sum":     "sum",
    "any":     "any",
    "all":     "all",
    "count":   "_count",    # _count(seq, x) → number of occurrences
    # type/shape conversions
    "set":     "set",
    "list":    "list",
    "tuple":   "tuple",
    "dict":    "dict",
    "str":     "str",
    "int":     "int",
    # iteration helpers
    "range":   "range",
    "enumerate": "enumerate",
    "zip":     "zip",
    "map":     "map",
    "filter":  "filter",
    # functional helpers
    "join":    "_join",     # _join(sep, seq) — Pythonic str.join made functional
    "split":   "_split",    # _split(s, sep=None) → s.split(sep)
}

GRAMMAR_SPEC = """\
L-Script v0.2 — emit ONLY these symbols and ASCII tokens. NO comments, NO English.

═══ BLOCK CONSTRUCTS ═══
Every block opener (ℱ, ¿, ⧖) needs ITS OWN ⚀ closer. Count them before emitting!

  ℱname⇥a,b ... ⚀                    function (one ⚀)
  ¿cond⇥ ... ⚀                        if (one ⚀)
  ¿cond⇥ ... ¡⇥ ... ⚀                 if/else (still ONE ⚀)
  ¿cond⇥ ... ⁇cond⇥ ... ⚀             if/elif (still ONE ⚀)
  ¿cond⇥ ... ⁇cond⇥ ... ¡⇥ ... ⚀     if/elif/else, any number of ⁇ (one ⚀)
  ⧖v∈iter⇥ ... ⚀                      FOR (note the ∈)
  ⧖cond⇥ ... ⚀                        WHILE (no ∈)

═══ STATEMENTS (one per whitespace-separated token) ═══
  §X=expr                              assignment
  ⧉expr                                return
  ⊗                                    break
  ⊙                                    continue
  expr                                 bare expression / method call (e.g. L.append(x))

═══ ⍃ OPERATIONS — preferred over manual loops ═══
Sequence ops (POLYMORPHIC: str input returns str, list input returns list):
  ⍃sort(L)        sorted ascending
  ⍃rsort(L)       sorted descending
  ⍃rev(L)         reversed
  ⍃unique(L)      de-dup, preserves first-occurrence order

Aggregations:
  ⍃len(L)  ⍃max(L)  ⍃min(L)  ⍃sum(L)  ⍃any(L)  ⍃all(L)
  ⍃count(L,x)     occurrences of x in L

Type conversions: ⍃set, ⍃list, ⍃tuple, ⍃dict, ⍃str, ⍃int
Iteration helpers: ⍃range, ⍃enumerate, ⍃zip, ⍃map, ⍃filter
String helpers:
  ⍃join(sep,seq)  e.g. ⍃join('',L)  same as ''.join(L)
  ⍃split(s,sep)   e.g. ⍃split(s,',') same as s.split(',')
Literal: ⍃[a,b,c]  list literal

═══ EXPRESSION OPERATORS — use Python operators, NOT Unicode math ═══
  in, not in, and, or, not, ==, !=, <, <=, >, >=, +, -, *, /, //, %, **
The ∈ symbol is RESERVED for the for-loop header — never use as a binary op.
Method calls work: L.append(x), s.lower(), d.get(k), set.add(x), etc.

═══ AVAILABLE BUILTINS (no imports allowed) ═══
abs, all, any, bool, dict, divmod, enumerate, filter, float, frozenset,
int, isinstance, len, list, map, max, min, pow, range, reversed, round,
set, sorted, str, sum, tuple, zip, True, False, None
String slicing works: S[::-1], S[1:5], S[a:b:c]

═══ NAMING & STYLE ═══
Single uppercase letters or short tokens (L, S, X, Y, A, B, T, n, i, j).
NO spaces inside expressions. ONE space between top-level statements.
NO docstrings, NO type hints, NO imports, NO comments, NO print.

═══ EXAMPLES ═══

"Sort strings by length, dedupe":
  ℱf⇥L §U=⍃unique(L) ⧉⍃sort(U,key=len) ⚀

"Sum of even integers in [0, n)":
  ℱf⇥n §T=0 ⧖i∈range(n)⇥ ¿i%2==0⇥ §T=T+i ⚀ ⚀ ⧉T ⚀

"FizzBuzz to n (uses elif — flat, no nesting)":
  ℱf⇥n §L=⍃[] ⧖i∈range(1,n+1)⇥ ¿i%15==0⇥ L.append('FizzBuzz') ⁇i%3==0⇥ L.append('Fizz') ⁇i%5==0⇥ L.append('Buzz') ¡⇥ L.append(i) ⚀ ⚀ ⧉L ⚀

"While loop — collatz length":
  ℱf⇥n §C=0 ⧖n>1⇥ ¿n%2==0⇥ §n=n//2 ¡⇥ §n=3*n+1 ⚀ §C=C+1 ⚀ ⧉C ⚀

═══ OUTPUT RULE ═══
Emit ONE function definition starting with ℱf⇥... ending with ⚀.
The function MUST be named exactly `f`. Output ONLY raw L-Script — no prose,
no fences, no markdown.
"""
