# echo module (reference module for G1)

Four trivial tools that exist to prove the plumbing: registration, schema
generation, error mapping, timeout, cancellation, drain and reconnect.

| Tool | Signature | Result | risk |
|---|---|---|---|
| `echo` | `echo(text: str)` | `{"text": ..., "len": <chars>}` | low |
| `add` | `add(a: float, b: float)` | `{"sum": <number>}` | low |
| `sleep` | `sleep(ms: int)` (async) | `{"slept_ms": ms}` | low |
| `boom` | `boom(message: str)` | raises `INTERNAL` with `message` | low |

Boundaries: `text` is limited to 65519 UTF-8 bytes (`PAYLOAD_TOO_LARGE` above
it — one frame of plaintext), `ms` is an integer in `0…30000`, `add` accepts
numbers only (`bool` is rejected), and every argument not in the signature is
`INVALID_ARGUMENT`. There is no filesystem, network or subprocess access.

## Layout

```
modules/echo/
├── manifest.json            generated — never hand-edited
├── pyproject.toml
├── src/echo_module/
│   ├── tools.py             pure functions, stdlib only, no SDK import
│   └── server.py            ModuleApp + ToolSpec, only forwards
├── tests/test_tools.py      runs without vade-sdk installed
├── tests/test_server.py     skipped when vade-sdk is missing
├── Dockerfile               build from the REPO ROOT (needs sdk/python)
└── data/                    module key lives here (gitignored, volume it)
```

`manifest.json` is produced by the same function that feeds `module/register`:

```bash
PYTHONPATH=src python -m echo_module --print-manifest > manifest.json
PYTHONPATH=src python -m echo_module --print-manifest | diff - manifest.json   # empty
```

## Run

```bash
pip install -e sdk/python
pip install -e modules/echo

pytest modules/echo/tests -q                       # 19 tests, no core
python -m echo_module --check                      # exit 0
python -m echo_module --standalone echo --args '{"text":"hi"}'
# {"ok": true, "result": {"text": "hi", "len": 2}}
```

Against a core (needs the module key whitelisted and core's Noise public key):

```bash
CORE_PUBLIC_KEY=<64 hex> MODULE_KEY_PATH=data/module.key \
  python -m echo_module --core wss://127.0.0.1:8443
```

`--pair-code` is not usable yet (core only builds IK responders); see
`sdk/PYTHON_SDK.md` §5.

## Container

```bash
docker build -f modules/echo/Dockerfile -t vade-echo .
docker run --rm -v vade-echo-data:/data \
  -e CORE_PUBLIC_KEY=<64 hex> vade-echo
```

The image mounts `/data` and sets `MODULE_KEY_PATH=/data/module.key`: **the key
must survive the container**, otherwise the fingerprint changes and core's
whitelist rejects the module (AMEND-01). The image runs as uid 10001 with no
writable layer outside `/data`.

## The two rules this module demonstrates

1. `tools.py` does not import `vade_sdk` (checked by an AST test). Tools can be
   written, reviewed and tested before the SDK exists.
2. `server.py` contains no tool logic — it adapts metadata from the `@tool`
   decorator into `ToolSpec`s and translates `ToolFailure` into `ToolError`.
