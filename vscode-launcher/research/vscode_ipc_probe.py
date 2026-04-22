#!/usr/bin/env python3
"""
VSCode IPC protocol probe — POC only, not shipped with the launcher.

Speaks VSCode's internal Node-IPC protocol over the Unix socket that
`code --status` uses under the hood. Connects to the running VSCode
main process and calls `diagnostics.getMainDiagnostics()` to retrieve
per-window info (id, pid, title, folderURIs).

References (all in github.com/microsoft/vscode @ v1.116):
  src/vs/base/parts/ipc/common/ipc.ts           (serialize/deserialize, RequestType/ResponseType)
  src/vs/base/parts/ipc/common/ipc.net.ts       (Protocol framing, ProtocolMessageType)
  src/vs/base/parts/ipc/node/ipc.net.ts         (connect, Client, sockets)
  src/vs/platform/diagnostics/electron-main/diagnosticsMainService.ts
                                                 (getMainDiagnostics payload shape)
  src/vs/code/electron-main/main.ts             (how the "other instance" client is used)

Wire protocol in a nutshell
---------------------------
1. 13-byte framing header:
     byte 0       : ProtocolMessageType   (uint8)
     bytes 1..4   : id                     (uint32 BE)
     bytes 5..8   : ack                    (uint32 BE)
     bytes 9..12  : body length            (uint32 BE)
   ProtocolMessageType.Regular = 1. id/ack = 0 works for a simple one-shot
   client — keepalive/ack tracking is only needed for long-lived connections.

2. The body carries VSBuffer-serialized data, which is tagged TLV:
     tag byte      : DataType
                     0 = undefined
                     1 = string        (followed by VQL length, then UTF-8 bytes)
                     2 = native Buffer (unused by us)
                     3 = VSBuffer      (unused by us)
                     4 = Array         (followed by VQL length, then N serialized elems)
                     5 = Object        (followed by VQL length, then JSON string)
                     6 = Int           (VQL int)
   VQL = variable-length 7-bit varint, little-endian continuation (high bit set
   means "more bytes to follow"). Zero is a single 0x00.

3. Handshake (from IPCClient constructor):
     - Client sends ONE Regular frame whose body is serialized(ctx_string).
     - Server sends back a Regular frame whose body is serialized([200]) — that's
       ResponseType.Initialize.
   Both happen essentially concurrently.

4. RPC call (from ChannelClient.sendRequest):
     - body = serialize(header) || serialize(arg)
       header = [100 /* RequestType.Promise */, request_id, channel_name, method_name]
     - Server replies with:
       body = serialize(response_header) || serialize(response_body)
       response_header = [201 /* PromiseSuccess */, request_id]
       response_body   = the method's return value

This probe only implements what's needed to make one call and read the reply.
No keepalive, no ack handling, no reconnection. Don't ship this as production
code — use it as a reference for a hardened Python client.
"""

from __future__ import annotations

import os
import socket
import struct
import sys
import time
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# VQL (variable-length quantity) codec
# -----------------------------------------------------------------------------


def read_vql(data: bytes, offset: int) -> tuple[int, int]:
    """Read a VQL-encoded non-negative integer starting at `offset`.
    Returns (value, new_offset)."""
    value = 0
    shift = 0
    while True:
        b = data[offset]
        offset += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, offset
        shift += 7


def write_vql(value: int) -> bytes:
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

# DataType enum from vs/base/parts/ipc/common/ipc.ts — names kept aligned.
DT_UNDEFINED = 0
DT_STRING = 1
DT_BUFFER = 2  # native node Buffer
DT_VSBUFFER = 3
DT_ARRAY = 4
DT_OBJECT = 5
DT_INT = 6


def serialize(data: Any) -> bytes:
    if data is None:
        return bytes([DT_UNDEFINED])
    if isinstance(data, bool):
        # Python bool is int subclass — handle explicitly as JSON object.
        body = __import__("json").dumps(data).encode("utf-8")
        return bytes([DT_OBJECT]) + write_vql(len(body)) + body
    if isinstance(data, str):
        body = data.encode("utf-8")
        return bytes([DT_STRING]) + write_vql(len(body)) + body
    if isinstance(data, int):
        return bytes([DT_INT]) + write_vql(data)
    if isinstance(data, list):
        out = bytes([DT_ARRAY]) + write_vql(len(data))
        for el in data:
            out += serialize(el)
        return out
    # Fallback: JSON-encoded "Object"
    body = __import__("json").dumps(data).encode("utf-8")
    return bytes([DT_OBJECT]) + write_vql(len(body)) + body


def deserialize(data: bytes, offset: int = 0) -> tuple[Any, int]:
    tag = data[offset]
    offset += 1
    if tag == DT_UNDEFINED:
        return None, offset
    if tag == DT_STRING:
        length, offset = read_vql(data, offset)
        value = data[offset : offset + length].decode("utf-8")
        return value, offset + length
    if tag == DT_BUFFER:
        length, offset = read_vql(data, offset)
        return data[offset : offset + length], offset + length
    if tag == DT_VSBUFFER:
        length, offset = read_vql(data, offset)
        return data[offset : offset + length], offset + length
    if tag == DT_ARRAY:
        length, offset = read_vql(data, offset)
        out: list[Any] = []
        for _ in range(length):
            element, offset = deserialize(data, offset)
            out.append(element)
        return out, offset
    if tag == DT_OBJECT:
        import json

        length, offset = read_vql(data, offset)
        value = json.loads(data[offset : offset + length].decode("utf-8"))
        return value, offset + length
    if tag == DT_INT:
        value, offset = read_vql(data, offset)
        return value, offset
    raise ValueError(f"unknown DataType tag: {tag}")


# -----------------------------------------------------------------------------
# Framing layer
# -----------------------------------------------------------------------------

PMT_REGULAR = 1
PMT_CONTROL = 2
PMT_ACK = 3
PMT_DISCONNECT = 5
PMT_KEEPALIVE = 9


def frame_regular(body: bytes, id_: int = 0, ack: int = 0) -> bytes:
    """Wrap `body` in a Regular-typed 13-byte protocol header."""
    return struct.pack(">BIII", PMT_REGULAR, id_, ack, len(body)) + body


def read_one_frame(sock: socket.socket, timeout: float = 5.0) -> tuple[int, bytes]:
    """Read exactly one framed protocol message from `sock`. Returns (type, body)."""
    sock.settimeout(timeout)
    header = _recv_exact(sock, 13)
    msg_type = header[0]
    body_len = struct.unpack(">I", header[9:13])[0]
    body = _recv_exact(sock, body_len) if body_len else b""
    return msg_type, body


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(f"socket closed after {len(buf)} of {n} bytes")
        buf.extend(chunk)
    return bytes(buf)


# -----------------------------------------------------------------------------
# Socket discovery
# -----------------------------------------------------------------------------


def find_main_socket() -> Path | None:
    """Locate the VSCode main IPC socket. Matches
    `vscode-<session>-<version>-main.sock` (newer) or `vscode-<session>-main.sock`."""
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    candidates = sorted(runtime_dir.glob("vscode-*-main.sock"))
    # Pick the most recently-modified — that's the actively-running instance.
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


# -----------------------------------------------------------------------------
# RPC
# -----------------------------------------------------------------------------

RT_PROMISE = 100  # RequestType.Promise
RST_INITIALIZE = 200
RST_PROMISE_SUCCESS = 201
RST_PROMISE_ERROR = 202
RST_PROMISE_ERROR_OBJ = 203


def call_channel(
    sock: socket.socket, channel: str, method: str, arg: Any = None, request_id: int = 1
) -> Any:
    """Invoke `method` on `channel` and return the deserialized result.

    Assumes the handshake has already happened (client ctx was sent).
    """
    header = [RT_PROMISE, request_id, channel, method]
    body = serialize(header) + serialize(arg)
    sock.sendall(frame_regular(body))

    # Read frames until we get the matching promise response.
    while True:
        msg_type, body = read_one_frame(sock)
        if msg_type != PMT_REGULAR:
            continue  # skip control / ack / keepalive
        resp_header, offset = deserialize(body, 0)
        if not isinstance(resp_header, list) or not resp_header:
            continue
        resp_type = resp_header[0]
        if resp_type == RST_INITIALIZE:
            # Server's initialize — ignore, keep reading.
            continue
        if resp_type == RST_PROMISE_SUCCESS and resp_header[1] == request_id:
            data, _ = deserialize(body, offset)
            return data
        if resp_type in (RST_PROMISE_ERROR, RST_PROMISE_ERROR_OBJ) and resp_header[1] == request_id:
            data, _ = deserialize(body, offset)
            raise RuntimeError(f"RPC error: {data}")


def get_main_diagnostics(sock_path: Path) -> dict[str, Any]:
    """Connect to the VSCode main socket and call getMainDiagnostics().
    Returns the full diagnostics payload as a dict."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(str(sock_path))
    try:
        # Client handshake: send ctx string (anything works; VSCode uses "main"
        # for the Electron-main-to-Electron-main case, but a probe ID is fine).
        s.sendall(frame_regular(serialize("vscl-probe")))
        # Call diagnostics.getMainDiagnostics — same RPC invocation ProxyChannel
        # would issue, minus the async plumbing.
        return call_channel(s, "diagnostics", "getMainDiagnostics")
    finally:
        s.close()


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    sock_path = find_main_socket()
    if sock_path is None:
        print("no VSCode main socket found under $XDG_RUNTIME_DIR", file=sys.stderr)
        return 1
    print(f"socket: {sock_path}")

    t0 = time.monotonic()
    result = get_main_diagnostics(sock_path)
    elapsed = (time.monotonic() - t0) * 1000

    print(f"RPC round-trip: {elapsed:.1f} ms")
    print(f"mainPID: {result.get('mainPID')}")
    print(f"windows: {len(result.get('windows', []))}")
    for w in result.get("windows", []):
        folder_uris = w.get("folderURIs", []) or []
        folders = [fu.get("path") if isinstance(fu, dict) else str(fu) for fu in folder_uris]
        print(
            f"  id={w.get('id')} pid={w.get('pid')} title={w.get('title')!r}"
            f" folders={folders}"
        )
    if "--verbose" in argv:
        import json

        print("--- full payload ---")
        print(json.dumps(result, indent=2, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
