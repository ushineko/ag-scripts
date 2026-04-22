"""VSCode internal IPC protocol client.

Speaks the Node-IPC wire protocol VSCode uses between its CLI and the running
main Electron process. See research/README.md for the reverse-engineering
writeup; this module is the production version.

Exposes one high-level entry point:

    entries = list_vscode_entries()

which returns a list of `WindowEntry` dicts — one per currently-open VSCode
window — or `None` if the IPC call fails. Returns `[]` when VSCode is not
running at all (no socket found).

Each WindowEntry is:
    {
        "id": int,                    # VSCode's internal window id
        "pid": int,                   # renderer PID (per-window!)
        "title": str,                 # window caption
        "folderURIs": list[dict],     # [{scheme, authority, path, ...}, ...]
        "remoteAuthority": str | None,
    }

The round-trip cost is ~2–3 ms, small enough to invoke directly from the UI
thread. This replaces the v1.x KWin-scripting + journalctl approach, which
was KDE-only and took ~500 ms per scan.
"""

from __future__ import annotations

import json
import socket
import struct
from pathlib import Path
from typing import Any, TypedDict

from platform_support import vscode_ipc_socket_candidates

# -----------------------------------------------------------------------------
# Protocol constants (from vs/base/parts/ipc/common/ipc.ts + ipc.net.ts)
# -----------------------------------------------------------------------------

# VSBuffer DataType tags (1 byte each)
_DT_UNDEFINED = 0
_DT_STRING = 1
_DT_BUFFER = 2
_DT_VSBUFFER = 3
_DT_ARRAY = 4
_DT_OBJECT = 5
_DT_INT = 6

# ProtocolMessageType — only Regular matters for a one-shot client
_PMT_REGULAR = 1

# RequestType / ResponseType
_RT_PROMISE = 100
_RST_INITIALIZE = 200
_RST_PROMISE_SUCCESS = 201
_RST_PROMISE_ERROR = 202
_RST_PROMISE_ERROR_OBJ = 203

_HEADER_STRUCT = struct.Struct(">BIII")  # msg_type, id, ack, body_len
_HEADER_SIZE = _HEADER_STRUCT.size  # 13 bytes

_DEFAULT_TIMEOUT = 2.0
_CLIENT_CTX = "vscode-launcher"


# -----------------------------------------------------------------------------
# Data shape (TypedDict for clarity, callers can treat as plain dict)
# -----------------------------------------------------------------------------


class WindowEntry(TypedDict, total=False):
    id: int
    pid: int
    title: str
    folderURIs: list[dict]
    remoteAuthority: str | None


# -----------------------------------------------------------------------------
# VQL codec (7-bit-per-byte varint, high bit = continuation)
# -----------------------------------------------------------------------------


def _read_vql(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        b = data[offset]
        offset += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, offset
        shift += 7


def _write_vql(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    out = bytearray()
    while value > 0:
        byte = value & 0x7F
        value >>= 7
        if value > 0:
            byte |= 0x80
        out.append(byte)
    return bytes(out)


# -----------------------------------------------------------------------------
# VSBuffer serialize / deserialize
# -----------------------------------------------------------------------------


def _serialize(data: Any) -> bytes:
    if data is None:
        return bytes([_DT_UNDEFINED])
    # bool subclasses int; handle before int check so True/False become
    # JSON-encoded "Object" as VSCode does.
    if isinstance(data, bool):
        body = json.dumps(data).encode("utf-8")
        return bytes([_DT_OBJECT]) + _write_vql(len(body)) + body
    if isinstance(data, str):
        body = data.encode("utf-8")
        return bytes([_DT_STRING]) + _write_vql(len(body)) + body
    if isinstance(data, int):
        return bytes([_DT_INT]) + _write_vql(data)
    if isinstance(data, list):
        out = bytes([_DT_ARRAY]) + _write_vql(len(data))
        for el in data:
            out += _serialize(el)
        return out
    body = json.dumps(data).encode("utf-8")
    return bytes([_DT_OBJECT]) + _write_vql(len(body)) + body


def _deserialize(data: bytes, offset: int = 0) -> tuple[Any, int]:
    tag = data[offset]
    offset += 1
    if tag == _DT_UNDEFINED:
        return None, offset
    if tag == _DT_STRING:
        length, offset = _read_vql(data, offset)
        return data[offset : offset + length].decode("utf-8"), offset + length
    if tag in (_DT_BUFFER, _DT_VSBUFFER):
        length, offset = _read_vql(data, offset)
        return data[offset : offset + length], offset + length
    if tag == _DT_ARRAY:
        length, offset = _read_vql(data, offset)
        items: list[Any] = []
        for _ in range(length):
            element, offset = _deserialize(data, offset)
            items.append(element)
        return items, offset
    if tag == _DT_OBJECT:
        length, offset = _read_vql(data, offset)
        value = json.loads(data[offset : offset + length].decode("utf-8"))
        return value, offset + length
    if tag == _DT_INT:
        value, offset = _read_vql(data, offset)
        return value, offset
    raise ValueError(f"unknown VSBuffer DataType tag: {tag}")


# -----------------------------------------------------------------------------
# Framing
# -----------------------------------------------------------------------------


def _frame_regular(body: bytes) -> bytes:
    return _HEADER_STRUCT.pack(_PMT_REGULAR, 0, 0, len(body)) + body


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(f"socket closed after {len(buf)} of {n} bytes")
        buf.extend(chunk)
    return bytes(buf)


def _read_frame(sock: socket.socket) -> tuple[int, bytes]:
    header = _recv_exact(sock, _HEADER_SIZE)
    msg_type, _id, _ack, body_len = _HEADER_STRUCT.unpack(header)
    body = _recv_exact(sock, body_len) if body_len else b""
    return msg_type, body


# -----------------------------------------------------------------------------
# Socket discovery
# -----------------------------------------------------------------------------


def find_main_socket() -> Path | None:
    """Return the most-recent VSCode main IPC socket path, or None if
    VSCode isn't running (or the current platform isn't supported yet).
    Thin wrapper over `platform_support.vscode_ipc_socket_candidates()`."""
    candidates = vscode_ipc_socket_candidates()
    return candidates[0] if candidates else None


# -----------------------------------------------------------------------------
# Client
# -----------------------------------------------------------------------------


class VSCodeIPCError(Exception):
    """Raised on any protocol-level failure. Caller should treat as a
    transient error and retry rather than crash."""


def _call_channel(
    sock: socket.socket,
    channel: str,
    method: str,
    arg: Any = None,
    request_id: int = 1,
) -> Any:
    """Invoke `method` on `channel`, return the deserialized result. Assumes
    the client handshake (send-ctx) has already been performed."""
    header = [_RT_PROMISE, request_id, channel, method]
    sock.sendall(_frame_regular(_serialize(header) + _serialize(arg)))

    # Read frames until we find the matching promise response, skipping any
    # Initialize (type 200), ack, keepalive, or foreign-id replies.
    while True:
        msg_type, body = _read_frame(sock)
        if msg_type != _PMT_REGULAR or not body:
            continue
        try:
            resp_header, offset = _deserialize(body, 0)
        except (IndexError, ValueError, UnicodeDecodeError) as e:
            raise VSCodeIPCError(f"malformed response header: {e}") from e
        if not isinstance(resp_header, list) or len(resp_header) < 1:
            continue
        resp_type = resp_header[0]
        if resp_type == _RST_INITIALIZE:
            continue
        # Responses for our id
        if len(resp_header) >= 2 and resp_header[1] == request_id:
            if resp_type == _RST_PROMISE_SUCCESS:
                data, _ = _deserialize(body, offset)
                return data
            if resp_type in (_RST_PROMISE_ERROR, _RST_PROMISE_ERROR_OBJ):
                data, _ = _deserialize(body, offset)
                raise VSCodeIPCError(f"server returned error: {data!r}")


def get_main_diagnostics(
    sock_path: Path | None = None, timeout: float = _DEFAULT_TIMEOUT
) -> dict[str, Any] | None:
    """Connect to the VSCode main socket and call `diagnostics.getMainDiagnostics`.

    Returns the full payload dict on success, or None on any transient failure
    (no socket, connection refused, timeout, protocol error). The caller is
    expected to treat None as "try again next tick".
    """
    if sock_path is None:
        sock_path = find_main_socket()
    if sock_path is None:
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock_path))
            # Handshake: client sends ctx string as a Regular frame.
            s.sendall(_frame_regular(_serialize(_CLIENT_CTX)))
            return _call_channel(s, "diagnostics", "getMainDiagnostics")
    except (OSError, VSCodeIPCError):
        return None


def list_vscode_windows(
    sock_path: Path | None = None, timeout: float = _DEFAULT_TIMEOUT
) -> list[WindowEntry] | None:
    """Shorthand for callers that only care about the per-window info.

    Returns the list of WindowEntry dicts on success, or None on any
    transient IPC failure. A successful call where VSCode has no windows
    open returns []. A call where VSCode isn't running at all also
    returns []  — the semantic distinction between "can't tell" and
    "nothing is running" collapses here: no socket → no VSCode → no windows.
    """
    if sock_path is None and find_main_socket() is None:
        # No VSCode running → no open windows. Distinct from an IPC error.
        return []
    diagnostics = get_main_diagnostics(sock_path, timeout=timeout)
    if diagnostics is None:
        return None
    windows = diagnostics.get("windows") or []
    return [w for w in windows if isinstance(w, dict)]
