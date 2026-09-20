"""Narrow static anti-cheat checks with explicit deferred-stub allowance."""

from __future__ import annotations

import ast
import re

from fix_cli_codex_common import ROOT, TamperFailure

_DEFERRED = {
    ("provider.py", "recent_files"),
    ("provider.py", "search"),
    ("provider.py", "get_session"),
}


def scan() -> None:
    product = ROOT / "src/session_recall/providers/codex"
    tests = product / "tests"
    marker_patterns = (
        re.compile(r"pytest\.(?:skip|xfail)\s*\("),
        re.compile(r"@pytest\.mark\.(?:skip|xfail)\b"),
        re.compile(r"^\s*except\s*:\s*$", re.MULTILINE),
    )
    bad: list[str] = []
    for path in sorted(tests.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in marker_patterns):
            bad.append(f"test suppression/bare except: {path.relative_to(ROOT)}")
    for path in sorted(product.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if marker_patterns[2].search(text):
            bad.append(f"bare except: {path.relative_to(ROOT)}")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            bad.append(f"syntax error: {path.relative_to(ROOT)}:{exc.lineno}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = {
                getattr(item, "id", None) or getattr(item, "attr", None)
                for item in node.decorator_list
            }
            if "abstractmethod" in decorators or (path.name, node.name) in _DEFERRED:
                continue
            body = list(node.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            placeholder = not body
            if len(body) == 1:
                statement = body[0]
                placeholder |= isinstance(statement, ast.Pass)
                placeholder |= (isinstance(statement, ast.Expr)
                                and isinstance(statement.value, ast.Constant)
                                and statement.value.value is Ellipsis)
                if isinstance(statement, ast.Raise):
                    exc = statement.exc
                    placeholder |= (isinstance(exc, ast.Name)
                                    and exc.id == "NotImplementedError")
                    placeholder |= (isinstance(exc, ast.Call)
                                    and getattr(exc.func, "id", "") == "NotImplementedError")
            if placeholder:
                bad.append(f"placeholder: {path.relative_to(ROOT)}:{node.lineno}:{node.name}")
    if bad:
        raise TamperFailure("; ".join(bad))
