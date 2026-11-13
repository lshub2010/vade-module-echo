"""Adapter tests: manifest identity, schema generation, permission/argument edges.

Skipped entirely when the SDK is not installed, so `pytest modules/echo/tests`
still runs on a bare Python (that is the module's own gate).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT.parents[1] / "sdk" / "python"))

pytest.importorskip("vade_sdk", reason="vade-sdk is required for the adapter tests")

from echo_module import server, tools  # noqa: E402


@pytest.fixture()
def app():
    return server.build_app()


def test_module_identity_is_stable():
    assert server.MODULE_ID == "com.example.echo"
    assert server.MODULE_VERSION == "1.0.0"


def test_committed_manifest_matches_print_manifest(app):
    committed = json.loads((MODULE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert app.manifest() == committed


def test_check_is_clean(app):
    assert app.check() == []


def test_schema_comes_from_the_tool_signature(app):
    schema = app.tool("echo").input_schema
    assert schema["required"] == ["text"]
    assert schema["properties"]["text"] == {"type": "string"}
    assert app.tool("add").input_schema["properties"]["a"] == {"type": "number"}


def test_tool_metadata_comes_from_the_decorator(app):
    for fn in tools.all_tools():
        meta = fn.tool_meta
        spec = app.tool(meta["name"])
        assert spec.description == meta["description"]
        assert spec.risk == meta["risk"] == "low"
        assert spec.timeout_ms == meta["timeout_ms"]
        assert spec.idempotent is meta["idempotent"]


async def test_structured_tool_error_keeps_its_code(app):
    envelope = await app.call_tool("boom", {"message": "kaboom"})
    assert envelope["ok"] is False
    assert envelope["error"] == {"code": "INTERNAL", "message": "kaboom", "retriable": False}


async def test_overreach_argument_is_rejected(app):
    envelope = await app.call_tool("echo", {"text": "hi", "path": "../../etc/passwd"})
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "INVALID_ARGUMENT"


async def test_unknown_tool_is_not_found(app):
    assert (await app.call_tool("shell_exec", {"cmd": "id"}))["error"]["code"] == "NOT_FOUND"


async def test_wrong_type_is_rejected_by_the_sdk(app):
    assert (await app.call_tool("add", {"a": "1", "b": 2}))["error"]["code"] == "INVALID_ARGUMENT"


def test_standalone_entrypoint_output():
    """The real CLI, in a fresh interpreter (no event loop from pytest)."""
    import os
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(MODULE_ROOT / "src"), str(MODULE_ROOT.parents[1] / "sdk" / "python"), env.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "echo_module", "--standalone", "echo", "--args", '{"text":"hi"}'],
        cwd=MODULE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True, "result": {"text": "hi", "len": 2}}
    assert "tool ok" in completed.stderr


def test_print_manifest_is_byte_identical_to_the_committed_file():
    import os
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(MODULE_ROOT / "src"), str(MODULE_ROOT.parents[1] / "sdk" / "python"), env.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "echo_module", "--print-manifest"],
        cwd=MODULE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == (MODULE_ROOT / "manifest.json").read_text(encoding="utf-8")
