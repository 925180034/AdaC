"""Static checks for Python 3.10 deployment compatibility."""

from __future__ import annotations

import ast
from pathlib import Path


PY311_TYPING_NAMES = {"LiteralString", "NotRequired", "Self"}


def test_python310_compatible_typing_imports() -> None:
    """Require Python 3.11-only typing helpers to come from typing_extensions."""
    offenders: list[str] = []
    for path in sorted(Path("adacascade").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                imported = {alias.name for alias in node.names}
                blocked = sorted(imported & PY311_TYPING_NAMES)
                if blocked:
                    offenders.append(f"{path}: {', '.join(blocked)}")

    assert offenders == []
