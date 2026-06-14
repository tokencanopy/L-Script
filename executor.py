"""Restricted exec sandbox for parsed L-Script code."""

from __future__ import annotations

import ast
import builtins
from typing import Any

_ALLOWED_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "frozenset", "int", "isinstance", "len", "list", "map", "max",
    "min", "pow", "range", "reversed", "round", "set", "sorted", "str", "sum",
    "tuple", "zip", "True", "False", "None",
}

_BLOCKED_NAMES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "open",
    "exec", "eval", "compile", "__import__", "globals", "locals", "vars",
    "input", "exit", "quit", "help",
}


def _uniq(seq):
    """Order-preserving unique. Polymorphic: str→str, else list."""
    out, seen = [], set()
    for x in seq:
        try:
            if x in seen:
                continue
            seen.add(x)
        except TypeError:
            if any(x == s for s in out):
                continue
        out.append(x)
    return "".join(out) if isinstance(seq, str) else out


def _rev(x):
    """Reversed sequence. Polymorphic over str / list / tuple."""
    if isinstance(x, str):
        return x[::-1]
    if isinstance(x, tuple):
        return tuple(reversed(x))
    return list(reversed(x))


def _sort(x, **kw):
    """Sorted sequence. Polymorphic: str input → str output."""
    s = sorted(x, **kw)
    return "".join(s) if isinstance(x, str) else s


def _rsort(x, **kw):
    kw.setdefault("reverse", True)
    if not kw["reverse"]:
        kw["reverse"] = True
    return _sort(x, **kw)


def _count(seq, target):
    """Count occurrences of target in seq."""
    return sum(1 for x in seq if x == target)


def _join(sep, seq):
    """Functional str.join — sep.join(seq), with str coercion."""
    return sep.join(str(x) for x in seq)


def _split(s, sep=None):
    """Functional str.split."""
    return s.split(sep)


def _safe_globals() -> dict[str, Any]:
    safe_builtins = {name: getattr(builtins, name) for name in _ALLOWED_BUILTINS}
    return {
        "__builtins__": safe_builtins,
        "_uniq": _uniq,
        "_rev": _rev,
        "_sort": _sort,
        "_rsort": _rsort,
        "_count": _count,
        "_join": _join,
        "_split": _split,
    }


def _audit(static_src: str) -> None:
    """AST scan: reject imports and references to blocked names."""
    try:
        tree = ast.parse(static_src)
    except SyntaxError as e:
        raise SyntaxError(f"sandbox: invalid syntax in compiled code: {e}") from e

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise PermissionError("sandbox: import statements are forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise PermissionError(f"sandbox: dunder attribute access forbidden ({node.attr!r})")
        if isinstance(node, ast.Name) and node.id in _BLOCKED_NAMES:
            raise PermissionError(f"sandbox: blocked name {node.id!r}")


def run_sandboxed(python_src: str, fn_name: str = "f") -> Any:
    """Compile python_src in a restricted scope and return the named function.

    Raises PermissionError if blocked names appear. The returned callable
    closes over the sandboxed globals — calling it stays inside the sandbox.
    """
    _audit(python_src)
    g = _safe_globals()
    code = compile(python_src, "<lscript>", "exec")
    exec(code, g)
    fn = g.get(fn_name)
    if fn is None:
        raise NameError(f"compiled code did not define {fn_name!r}")
    return fn
