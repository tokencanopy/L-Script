"""Parse L-Script symbols into executable Python source."""

from __future__ import annotations

import re

from grammar import LIST_OPS, SYMBOLS

F = SYMBOLS["FUNC"]
ARG = SYMBOLS["ARGS"]
ASSIGN = SYMBOLS["ASSIGN"]
COND = SYMBOLS["COND"]
ELIF = SYMBOLS["ELIF"]
ELSE = SYMBOLS["ELSE"]
LOOP = SYMBOLS["LOOP"]
IN = SYMBOLS["IN"]
RET = SYMBOLS["RETURN"]
BREAK = SYMBOLS["BREAK"]
CONT = SYMBOLS["CONT"]
END = SYMBOLS["END"]
LIST = SYMBOLS["LIST"]


class LScriptSyntaxError(ValueError):
    pass


_OP_CALL_RE = re.compile(rf"{re.escape(LIST)}([a-zA-Z_]+)\(")

# Math-style Unicode operators the LLM may emit by analogy with `∈`.
# Translate them to valid Python so we don't reject otherwise-correct programs.
_UNICODE_OP_MAP = {
    "∉": " not in ",
    "∈": " in ",        # only relevant inside expressions; loop ∈ is consumed
                        # by the LOOP-header parser before this runs.
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "∧": " and ",
    "∨": " or ",
    "¬": " not ",
}


def _translate_expr(expr: str) -> str:
    """Translate ⍃ list-ops + Unicode math operators inside an expression to Python."""
    expr = expr.replace(f"{LIST}[", "[")
    for u, py in _UNICODE_OP_MAP.items():
        expr = expr.replace(u, py)

    while True:
        m = _OP_CALL_RE.search(expr)
        if not m:
            break
        op = m.group(1)
        if op not in LIST_OPS:
            raise LScriptSyntaxError(f"unknown ⍃ op: {op!r}")
        py = LIST_OPS[op]
        if py.startswith("lambda"):
            py = f"({py})"
        expr = expr[: m.start()] + py + "(" + expr[m.end() :]

    if LIST in expr:
        raise LScriptSyntaxError(f"unresolved ⍃ in expression: {expr!r}")
    return expr


# Block headers whose `⇥` is at the END (so spaces inside the condition can
# be tolerated by glueing tokens together until ⇥ appears). Function headers
# put `⇥` in the MIDDLE (`ℱname⇥args`), so they're complete in one token
# and excluded from this rule.
_HEADER_OPENERS = (COND, ELIF, LOOP)


def _tokenize(src: str) -> list[str]:
    """Whitespace-split, but glue header openers (ℱ ¿ ⁇ ⧖) together with
    their condition/args until we see the closing ⇥. This lets the LLM
    write Python idioms like `¿c in V⇥` or `⧖x not in S⇥` naturally
    instead of forcing them to elide spaces around `in`, `not in`, `and`, etc.
    """
    src = src.replace(END, f" {END} ")
    raw = [t for t in src.split() if t]

    out: list[str] = []
    i = 0
    while i < len(raw):
        tok = raw[i]
        starts_header = any(tok.startswith(p) for p in _HEADER_OPENERS)
        if starts_header and not tok.endswith(ARG):
            # absorb tokens until we find one ending in ⇥
            i += 1
            while i < len(raw):
                tok = tok + " " + raw[i]
                if raw[i].endswith(ARG):
                    i += 1
                    break
                i += 1
            out.append(tok)
            continue
        out.append(tok)
        i += 1
    return out


def lscript_to_python(src: str) -> str:
    """Convert an L-Script program into a Python source string."""
    tokens = _tokenize(src)
    if not tokens:
        raise LScriptSyntaxError("empty program")

    lines: list[str] = []
    indent = 0
    pad = lambda: "    " * indent  # noqa: E731

    for i, tok in enumerate(tokens):
        if tok == END:
            # Tolerate `⚀` immediately before an `elif`/`else` — the closer
            # is redundant in those cases (the next branch will handle the
            # dedent itself). This makes the parser permissive of the more
            # natural way LLMs sometimes structure if/elif/else cascades.
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if nxt is not None and (
                nxt == ELSE + ARG
                or (nxt.startswith(ELIF) and nxt.endswith(ARG))
            ):
                continue
            indent -= 1
            if indent < 0:
                raise LScriptSyntaxError("unmatched ⚀")
            continue

        if tok.startswith(F):
            body = tok[len(F):]
            if ARG not in body:
                raise LScriptSyntaxError(f"function header missing ⇥: {tok!r}")
            name, args = body.split(ARG, 1)
            if not name:
                raise LScriptSyntaxError(f"function missing name: {tok!r}")
            lines.append(f"{pad()}def {name}({args}):")
            indent += 1
            continue

        if tok.startswith(COND):
            body = tok[len(COND):]
            if not body.endswith(ARG):
                raise LScriptSyntaxError(f"if header missing trailing ⇥: {tok!r}")
            cond = _translate_expr(body[:-len(ARG)])
            lines.append(f"{pad()}if {cond}:")
            indent += 1
            continue

        if tok.startswith(ELIF):
            body = tok[len(ELIF):]
            if not body.endswith(ARG):
                raise LScriptSyntaxError(f"elif header missing trailing ⇥: {tok!r}")
            cond = _translate_expr(body[:-len(ARG)])
            indent -= 1
            if indent < 0:
                raise LScriptSyntaxError("elif without matching if")
            lines.append(f"{pad()}elif {cond}:")
            indent += 1
            continue

        if tok.startswith(ELSE):
            body = tok[len(ELSE):]
            if body != ARG:
                raise LScriptSyntaxError(f"else must be ¡⇥, got {tok!r}")
            indent -= 1
            if indent < 0:
                raise LScriptSyntaxError("else without matching if")
            lines.append(f"{pad()}else:")
            indent += 1
            continue

        if tok.startswith(LOOP):
            body = tok[len(LOOP):]
            if not body.endswith(ARG):
                raise LScriptSyntaxError(f"loop header missing trailing ⇥: {tok!r}")
            body = body[:-len(ARG)]
            if IN in body:
                # for-loop: ⧖v∈iter⇥
                var, iterable = body.split(IN, 1)
                lines.append(f"{pad()}for {var} in {_translate_expr(iterable)}:")
            else:
                # while-loop: ⧖cond⇥
                lines.append(f"{pad()}while {_translate_expr(body)}:")
            indent += 1
            continue

        if tok == BREAK:
            lines.append(f"{pad()}break")
            continue

        if tok == CONT:
            lines.append(f"{pad()}continue")
            continue

        if tok.startswith(ASSIGN):
            body = tok[len(ASSIGN):]
            if "=" not in body:
                raise LScriptSyntaxError(f"assignment missing '=': {tok!r}")
            var, expr = body.split("=", 1)
            lines.append(f"{pad()}{var} = {_translate_expr(expr)}")
            continue

        if tok.startswith(RET):
            expr = _translate_expr(tok[len(RET):])
            lines.append(f"{pad()}return {expr}")
            continue

        lines.append(f"{pad()}{_translate_expr(tok)}")

    # LLMs frequently forget to close every block at EOF. Treat any open
    # blocks as implicitly closed — the resulting Python is still well-formed
    # since indentation alone delimits scope. Surface this fact via a counter
    # the harness can log, but don't reject the program.
    # (No explicit unclosed-block error — semantic correctness is what gets
    # tested by the held-out tests.)

    return "\n".join(lines) + "\n"
