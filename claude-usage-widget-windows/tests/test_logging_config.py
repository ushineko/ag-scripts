"""Tests for logging sink routing.

The terminal-display modes (--tui/--line) own the pane, so logs must never reach
the terminal — otherwise they interleave with the redrawn status line. These
tests pin that behavior (regression for the TUI log-interleaving bug).
"""

import io

import structlog

from src.logging_config import setup_logging


def _emit(message: str) -> None:
    structlog.get_logger().info(message, k="v")


class TestConsoleRouting:

    def test_console_true_writes_to_stream(self):
        buf = io.StringIO()
        setup_logging(debug=True, stream=buf, console=True)
        _emit("hello_console")
        assert "hello_console" in buf.getvalue()

    def test_console_false_discards_without_log_file(self, capsys):
        # No log_file -> devnull. Nothing on stdout or stderr.
        setup_logging(debug=True, console=False)
        _emit("should_not_appear")
        # print() (the display) is unaffected.
        print("display_line")
        captured = capsys.readouterr()
        assert "should_not_appear" not in captured.out
        assert "should_not_appear" not in captured.err
        assert "display_line" in captured.out

    def test_console_false_routes_to_log_file(self, tmp_path, capsys):
        log_file = tmp_path / "tui.log"
        setup_logging(debug=True, log_file=log_file, console=False)
        _emit("went_to_file")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert "went_to_file" in log_file.read_text()
