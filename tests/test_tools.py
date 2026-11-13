"""Echo tool tests — stdlib + pytest only, NO SDK import (module self-sufficiency).

If this file ever needs `vade_sdk`, the "write the module before the SDK"
guarantee is gone.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echo_module import tools  # noqa: E402


def test_no_sdk_import_in_tools():
    """AST check, not a substring scan: a docstring may *mention* the SDK."""
    import ast

    tree = ast.parse(Path(tools.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not [name for name in imported if name == "vade_sdk" or name.startswith("vade_sdk.")]
    assert not [name for name in imported if name == "vade" or name.startswith("vade.")]


def test_echo_returns_text_and_length():
    assert tools.echo("hi") == {"text": "hi", "len": 2}
    assert tools.echo("回声") == {"text": "回声", "len": 2}


def test_echo_rejects_non_string():
    with pytest.raises(tools.ToolFailure) as excinfo:
        tools.echo(123)  # type: ignore[arg-type]
    assert excinfo.value.code == "INVALID_ARGUMENT"


def test_echo_rejects_oversized_payload():
    with pytest.raises(tools.ToolFailure) as excinfo:
        tools.echo("x" * (tools.MAX_TEXT_BYTES + 1))
    assert excinfo.value.code == "PAYLOAD_TOO_LARGE"


def test_add_accepts_numbers_and_rejects_bool():
    assert tools.add(1, 2) == {"sum": 3.0}
    assert tools.add(1.5, -0.5) == {"sum": 1.0}
    with pytest.raises(tools.ToolFailure) as excinfo:
        tools.add(True, 1)  # type: ignore[arg-type]
    assert excinfo.value.code == "INVALID_ARGUMENT"


def test_sleep_is_awaitable_and_validates_ms():
    assert asyncio.run(tools.sleep(0)) == {"slept_ms": 0}
    with pytest.raises(tools.ToolFailure):
        asyncio.run(tools.sleep(-1))
    with pytest.raises(tools.ToolFailure):
        asyncio.run(tools.sleep(60_000))


def test_boom_raises_internal_with_the_given_message():
    with pytest.raises(tools.ToolFailure) as excinfo:
        tools.boom("kaboom")
    assert excinfo.value.code == "INTERNAL"
    assert excinfo.value.message == "kaboom"


def test_every_tool_is_decorated_and_unique():
    names = [fn.tool_meta["name"] for fn in tools.all_tools()]
    assert names == ["echo", "add", "sleep", "boom"]
    assert len(names) == len(set(names))
