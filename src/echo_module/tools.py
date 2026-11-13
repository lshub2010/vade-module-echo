"""Echo tools — pure functions, stdlib only, ZERO SDK imports.

This is the hard criterion for "module self-sufficiency" (design §15.1): the
files here must be writable and testable before the SDK exists, and a reviewer
must be able to run `pytest modules/echo/tests/test_tools.py` on a machine with
no vade-sdk installed.

The decorator below is the manifest source of truth for *metadata*. The JSON
Schema is still derived from each function's signature by the SDK — but the
name/description/risk/timeout/idempotent tuple lives here so `tools.py` alone
answers "what does this module offer".
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

__all__ = ["tool", "ToolFailure", "echo", "add", "sleep", "boom", "all_tools", "MAX_TEXT_BYTES"]

#: One frame of plaintext is 65519 bytes (C-01 §7.5); refuse locally with a
#: readable code instead of letting the transport drop the connection.
MAX_TEXT_BYTES = 65519


class ToolFailure(Exception):
    """A structured failure raised by a pure tool.

    Deliberately NOT `vade_sdk.ToolError`: importing the SDK here would break
    the "write and test tools before the SDK" rule. `server.py` translates
    this into a ToolError with the same C-04 code, so nothing is lost.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def tool(
    name: str,
    description: str,
    *,
    risk: str = "low",
    timeout_ms: int = 30_000,
    idempotent: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach manifest metadata to a function (no SDK, no validation logic)."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.tool_meta = {  # type: ignore[attr-defined]
            "name": name,
            "description": description,
            "risk": risk,
            "timeout_ms": timeout_ms,
            "idempotent": idempotent,
        }
        return fn

    return decorate


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ToolFailure("INVALID_ARGUMENT", f"{field} must be a string, got {type(value).__name__}")
    return value


def _require_number(value: Any, field: str) -> float:
    # bool is an int subclass; accepting `add(True, 1)` would be a silent
    # type hole the manifest says is a number.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolFailure("INVALID_ARGUMENT", f"{field} must be a number, got {type(value).__name__}")
    return float(value)


@tool("echo", "原样返回输入文本，并给出字符长度", timeout_ms=5_000, idempotent=True)
def echo(text: str) -> dict[str, Any]:
    """Return `{text, len}` unchanged."""
    text = _require_text(text, "text")
    size = len(text.encode("utf-8"))
    if size > MAX_TEXT_BYTES:
        raise ToolFailure("PAYLOAD_TOO_LARGE", f"text is {size} bytes; the frame limit is {MAX_TEXT_BYTES}")
    return {"text": text, "len": len(text)}


@tool("add", "两个数值相加，用于验证参数类型与返回值", timeout_ms=1_000, idempotent=True)
def add(a: float, b: float) -> dict[str, Any]:
    left = _require_number(a, "a")
    right = _require_number(b, "b")
    return {"sum": left + right}


@tool("sleep", "睡眠指定毫秒数；用于超时与取消的端到端验证", timeout_ms=30_000, idempotent=True)
async def sleep(ms: int) -> dict[str, Any]:
    if isinstance(ms, bool) or not isinstance(ms, int):
        raise ToolFailure("INVALID_ARGUMENT", f"ms must be an integer, got {type(ms).__name__}")
    if ms < 0:
        raise ToolFailure("INVALID_ARGUMENT", "ms must be >= 0")
    if ms > 30_000:
        raise ToolFailure("INVALID_ARGUMENT", "ms must be <= 30000 (the tool timeout)")
    await asyncio.sleep(ms / 1000.0)
    return {"slept_ms": ms}


@tool("boom", "总是抛出 INTERNAL 错误，用于验证错误通道", timeout_ms=1_000, idempotent=True)
def boom(message: str) -> dict[str, Any]:
    message = _require_text(message, "message")
    raise ToolFailure("INTERNAL", message)


def all_tools() -> tuple[Callable[..., Any], ...]:
    """Every decorated tool, in declaration order (manifest order is stable)."""
    return (echo, add, sleep, boom)
