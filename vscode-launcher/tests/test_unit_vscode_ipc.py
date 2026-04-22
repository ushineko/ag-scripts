"""Unit tests for vscode_ipc — VSCode internal IPC protocol client.

No live VSCode instance is required. The socket-roundtrip tests use an
AF_UNIX socketpair to stand in for the real VSCode socket, feeding framed
responses to the client.
"""

from __future__ import annotations

import socket
import struct
import threading
from unittest.mock import patch

import pytest

from vscode_ipc import (
    VSCodeIPCError,
    _call_channel,
    _deserialize,
    _frame_regular,
    _HEADER_STRUCT,
    _PMT_REGULAR,
    _read_vql,
    _RST_INITIALIZE,
    _RST_PROMISE_ERROR,
    _RST_PROMISE_SUCCESS,
    _serialize,
    _write_vql,
    find_main_socket,
    get_main_diagnostics,
    list_vscode_windows,
)


# ---------------------------------------------------------------------------
# VQL codec
# ---------------------------------------------------------------------------


class TestVQL:
    @pytest.mark.parametrize(
        "value,encoded",
        [
            (0, b"\x00"),
            (1, b"\x01"),
            (127, b"\x7f"),
            (128, b"\x80\x01"),
            (16383, b"\xff\x7f"),
            (16384, b"\x80\x80\x01"),
            (1_000_000, b"\xc0\x84\x3d"),
        ],
    )
    def test_round_trip(self, value, encoded):
        assert _write_vql(value) == encoded
        decoded, offset = _read_vql(encoded, 0)
        assert decoded == value
        assert offset == len(encoded)


# ---------------------------------------------------------------------------
# VSBuffer serialization
# ---------------------------------------------------------------------------


class TestVSBufferSerialize:
    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "hello",
            "unicode café ★",
            0,
            1,
            12345,
            [],
            ["a", "b", "c"],
            [1, 2, 3],
            [[1, 2], ["x"], []],
            {"key": "value", "n": 42},
            [{"inner": 1}, "str", 7],
            True,
            False,
        ],
    )
    def test_round_trip(self, value):
        encoded = _serialize(value)
        decoded, offset = _deserialize(encoded, 0)
        assert decoded == value
        assert offset == len(encoded)

    def test_nested_header_plus_body(self):
        """The real RPC body is two serialized values concatenated."""
        header = [100, 1, "diagnostics", "getMainDiagnostics"]
        arg = None
        buf = _serialize(header) + _serialize(arg)
        dec_header, off = _deserialize(buf, 0)
        dec_arg, _ = _deserialize(buf, off)
        assert dec_header == header
        assert dec_arg is None


# ---------------------------------------------------------------------------
# find_main_socket
# ---------------------------------------------------------------------------


class TestFindMainSocket:
    def test_returns_none_when_runtime_dir_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        assert find_main_socket() is None

    def test_picks_most_recent_of_multiple(self, tmp_path, monkeypatch):
        # Two candidate sockets; file mtimes set manually.
        old = tmp_path / "vscode-aaa-main.sock"
        new = tmp_path / "vscode-bbb-main.sock"
        old.touch()
        new.touch()
        import os

        os.utime(old, (1_000, 1_000))
        os.utime(new, (2_000, 2_000))
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        assert find_main_socket() == new

    def test_ignores_non_main_sockets(self, tmp_path, monkeypatch):
        (tmp_path / "vscode-git-abc.sock").touch()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        assert find_main_socket() is None


# ---------------------------------------------------------------------------
# Server-side test harness
# ---------------------------------------------------------------------------


def _send_frame(sock: socket.socket, body: bytes) -> None:
    """Convenience for the test-side fake server."""
    sock.sendall(_HEADER_STRUCT.pack(_PMT_REGULAR, 0, 0, len(body)) + body)


def _recv_frame(sock: socket.socket) -> tuple[int, bytes]:
    header = sock.recv(_HEADER_STRUCT.size)
    if len(header) < _HEADER_STRUCT.size:
        raise ConnectionError("short header")
    msg_type, _id, _ack, body_len = _HEADER_STRUCT.unpack(header)
    body = b""
    while len(body) < body_len:
        chunk = sock.recv(body_len - len(body))
        if not chunk:
            break
        body += chunk
    return msg_type, body


class TestCallChannel:
    def test_happy_path_promise_success(self):
        """Fake server sends Initialize, then a PromiseSuccess with our
        request id carrying a simple object payload. Client should receive
        the payload."""
        client_sock, server_sock = socket.socketpair()
        try:
            payload = {"windows": [{"id": 1, "pid": 42, "title": "A", "folderURIs": []}]}
            request_id = 7

            def server_thread():
                try:
                    # Expect the ctx handshake first.
                    _recv_frame(server_sock)
                    # Send Initialize (type 200) as a real server would.
                    _send_frame(server_sock, _serialize([_RST_INITIALIZE]))
                    # Expect the promise request.
                    _recv_frame(server_sock)
                    # Respond: [201, request_id] + payload
                    _send_frame(
                        server_sock,
                        _serialize([_RST_PROMISE_SUCCESS, request_id])
                        + _serialize(payload),
                    )
                finally:
                    server_sock.close()

            t = threading.Thread(target=server_thread, daemon=True)
            t.start()

            # Client must emit its own handshake before calling:
            client_sock.sendall(_frame_regular(_serialize("test-client")))
            result = _call_channel(
                client_sock, "diagnostics", "getMainDiagnostics", request_id=request_id
            )
            t.join(timeout=2.0)
            assert result == payload
        finally:
            client_sock.close()

    def test_promise_error_raises_vscode_ipc_error(self):
        client_sock, server_sock = socket.socketpair()
        try:
            request_id = 3

            def server_thread():
                try:
                    _recv_frame(server_sock)  # ctx
                    _send_frame(server_sock, _serialize([_RST_INITIALIZE]))
                    _recv_frame(server_sock)  # request
                    _send_frame(
                        server_sock,
                        _serialize([_RST_PROMISE_ERROR, request_id])
                        + _serialize(
                            {"message": "boom", "name": "Error", "stack": []}
                        ),
                    )
                finally:
                    server_sock.close()

            threading.Thread(target=server_thread, daemon=True).start()
            client_sock.sendall(_frame_regular(_serialize("test-client")))
            with pytest.raises(VSCodeIPCError):
                _call_channel(client_sock, "c", "m", request_id=request_id)
        finally:
            client_sock.close()

    def test_ignores_frames_for_other_ids(self):
        """Server replies with a response for a DIFFERENT id first; client
        should skip it and keep waiting for its own id."""
        client_sock, server_sock = socket.socketpair()
        try:
            our_id = 5

            def server_thread():
                try:
                    _recv_frame(server_sock)
                    _send_frame(server_sock, _serialize([_RST_INITIALIZE]))
                    _recv_frame(server_sock)
                    # Response for a different id (could be from a prior call in a
                    # long-lived connection)
                    _send_frame(
                        server_sock,
                        _serialize([_RST_PROMISE_SUCCESS, 999])
                        + _serialize({"old": True}),
                    )
                    # Then the one we're waiting for
                    _send_frame(
                        server_sock,
                        _serialize([_RST_PROMISE_SUCCESS, our_id])
                        + _serialize({"current": True}),
                    )
                finally:
                    server_sock.close()

            threading.Thread(target=server_thread, daemon=True).start()
            client_sock.sendall(_frame_regular(_serialize("test-client")))
            result = _call_channel(client_sock, "c", "m", request_id=our_id)
            assert result == {"current": True}
        finally:
            client_sock.close()


# ---------------------------------------------------------------------------
# get_main_diagnostics / list_vscode_windows — failure-mode integration
# ---------------------------------------------------------------------------


class TestHighLevelHelpers:
    def test_no_socket_returns_empty_list_not_none(self, tmp_path, monkeypatch):
        """When VSCode isn't running, list_vscode_windows distinguishes
        'nothing running' ([]) from 'transient IPC failure' (None)."""
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        assert list_vscode_windows() == []

    def test_get_main_diagnostics_none_when_no_socket(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        assert get_main_diagnostics() is None

    def test_connect_failure_returns_none(self, tmp_path, monkeypatch):
        """Socket exists (from a dead VSCode) but connection refused."""
        # Create a file that looks like a socket but isn't listening.
        fake_sock = tmp_path / "vscode-dead-main.sock"
        fake_sock.touch()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        # get_main_diagnostics should swallow the connection error.
        assert get_main_diagnostics() is None
