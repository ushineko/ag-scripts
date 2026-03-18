"""Tests for AudioPipeline and StreamScanner.

Mocks subprocess.run at the boundary to verify pactl commands
without requiring a running PulseAudio/PipeWire daemon.
"""

import json
import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_audio_rerouter import (
    APP_CAPTURE_PREFIX,
    COMBINED_SINK_NAME,
    AudioPipeline,
    StreamScanner,
    run_command,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_sink_input(index, app_name, media_name="", sink=0, extra_props=None):
    props = {"application.name": app_name, "media.name": media_name, "node.name": f"node_{index}"}
    if extra_props:
        props.update(extra_props)
    return {"index": index, "sink": sink, "properties": props}


def _make_sink(index, name):
    return {"index": index, "name": name}


def _make_source(name, description=None, extra_props=None):
    desc = name if description is None else description
    return {"name": name, "description": desc, "properties": extra_props or {}}


SAMPLE_SINKS = [
    _make_sink(0, "alsa_output.usb-speakers"),
    _make_sink(1, "alsa_output.hdmi"),
]

SAMPLE_SINK_INPUTS = [
    _make_sink_input(100, "Spotify", "Bohemian Rhapsody", sink=0),
    _make_sink_input(101, "Firefox", "YouTube", sink=0),
    _make_sink_input(102, "loopback", "Loopback", sink=1,
                     extra_props={"module-stream-restore.id": "module-loopback"}),
]

SAMPLE_SOURCES = [
    _make_source("alsa_input.usb-mic", "USB Microphone"),
    _make_source("alsa_input.webcam", "Webcam Mic"),
    _make_source("alsa_output.usb-speakers.monitor", "Monitor of USB Speakers"),
]


def _mock_subprocess_factory(responses=None):
    """Create a mock subprocess.run that returns canned responses based on command args.

    responses: dict mapping a key tuple of args to (stdout, returncode).
    Unmatched commands return ("", 0).
    """
    responses = responses or {}

    def mock_run(args, **kwargs):
        # Check for exact match first
        key = tuple(args)
        if key in responses:
            stdout, rc = responses[key]
            result = MagicMock()
            result.stdout = stdout
            result.stderr = ""
            result.returncode = rc
            if rc != 0 and kwargs.get("check"):
                raise subprocess.CalledProcessError(rc, args, output=stdout, stderr="")
            return result

        # Check for prefix matches (e.g., pactl --format=json list sink-inputs)
        for resp_key, (stdout, rc) in responses.items():
            if key[:len(resp_key)] == resp_key:
                result = MagicMock()
                result.stdout = stdout
                result.stderr = ""
                result.returncode = rc
                if rc != 0 and kwargs.get("check"):
                    raise subprocess.CalledProcessError(rc, args, output=stdout, stderr="")
                return result

        # Default: success with empty output
        result = MagicMock()
        result.stdout = ""
        result.stderr = ""
        result.returncode = 0
        return result

    return mock_run


# ---------------------------------------------------------------------------
# StreamScanner tests
# ---------------------------------------------------------------------------

class TestStreamScanner(unittest.TestCase):

    @patch("subprocess.run")
    def test_get_app_streams_filters_loopbacks(self, mock_run):
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (json.dumps(SAMPLE_SINK_INPUTS), 0),
            ("pactl", "--format=json", "list", "sinks"): (json.dumps(SAMPLE_SINKS), 0),
        })

        scanner = StreamScanner()
        streams = scanner.get_app_streams()

        # Should include Spotify and Firefox, but NOT the loopback stream
        names = [s.app_name for s in streams]
        self.assertIn("Spotify", names)
        self.assertIn("Firefox", names)
        self.assertNotIn("loopback", names)
        self.assertEqual(len(streams), 2)

    @patch("subprocess.run")
    def test_get_app_streams_filters_virtual_sinks(self, mock_run):
        """Streams on our own virtual sinks should be excluded."""
        inputs = [
            _make_sink_input(200, "Spotify", sink=0),
            _make_sink_input(201, "Captured", sink=5),  # On our intermediate sink
        ]
        sinks = SAMPLE_SINKS + [_make_sink(5, f"{APP_CAPTURE_PREFIX}201")]

        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (json.dumps(inputs), 0),
            ("pactl", "--format=json", "list", "sinks"): (json.dumps(sinks), 0),
        })

        scanner = StreamScanner()
        streams = scanner.get_app_streams()
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0].app_name, "Spotify")

    @patch("subprocess.run")
    def test_get_app_streams_filters_pipewire_internal(self, mock_run):
        """Streams from PipeWire itself should be excluded."""
        inputs = [
            _make_sink_input(300, "Spotify", sink=0),
            _make_sink_input(301, "PipeWire", "PipeWire Media Session", sink=0),
        ]
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (json.dumps(inputs), 0),
            ("pactl", "--format=json", "list", "sinks"): (json.dumps(SAMPLE_SINKS), 0),
        })

        scanner = StreamScanner()
        streams = scanner.get_app_streams()
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0].app_name, "Spotify")

    @patch("subprocess.run")
    def test_get_mic_sources_filters_monitors(self, mock_run):
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sources"): (json.dumps(SAMPLE_SOURCES), 0),
        })

        scanner = StreamScanner()
        sources = scanner.get_mic_sources()
        names = [s["name"] for s in sources]

        self.assertIn("alsa_input.usb-mic", names)
        self.assertIn("alsa_input.webcam", names)
        self.assertNotIn("alsa_output.usb-speakers.monitor", names)

    @patch("subprocess.run")
    def test_stream_exists_true(self, mock_run):
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (
                json.dumps([_make_sink_input(100, "Spotify")]), 0
            ),
        })
        scanner = StreamScanner()
        self.assertTrue(scanner.stream_exists(100))

    @patch("subprocess.run")
    def test_stream_exists_false(self, mock_run):
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (json.dumps([]), 0),
        })
        scanner = StreamScanner()
        self.assertFalse(scanner.stream_exists(100))

    @patch("subprocess.run")
    def test_display_name_app_and_media(self, mock_run):
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (
                json.dumps([_make_sink_input(1, "Firefox", "YouTube")]), 0
            ),
            ("pactl", "--format=json", "list", "sinks"): (json.dumps(SAMPLE_SINKS), 0),
        })
        scanner = StreamScanner()
        streams = scanner.get_app_streams()
        self.assertEqual(streams[0].display_name, "Firefox — YouTube")

    @patch("subprocess.run")
    def test_display_name_same_app_and_media(self, mock_run):
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (
                json.dumps([_make_sink_input(1, "Spotify", "Spotify")]), 0
            ),
            ("pactl", "--format=json", "list", "sinks"): (json.dumps(SAMPLE_SINKS), 0),
        })
        scanner = StreamScanner()
        streams = scanner.get_app_streams()
        self.assertEqual(streams[0].display_name, "Spotify")

    @patch("subprocess.run")
    def test_filters_loopback_media_name(self, mock_run):
        """Streams with media.name starting with 'loopback' should be excluded."""
        inputs = [
            _make_sink_input(40, "", "loopback-1626-13 output", sink=0),
            _make_sink_input(100, "Spotify", "Spotify", sink=0),
        ]
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (json.dumps(inputs), 0),
            ("pactl", "--format=json", "list", "sinks"): (json.dumps(SAMPLE_SINKS), 0),
        })
        scanner = StreamScanner()
        streams = scanner.get_app_streams()
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0].app_name, "Spotify")

    @patch("subprocess.run")
    def test_bluez_source_null_description_resolved(self, mock_run):
        """BlueZ sources with '(null)' description should use bluez.alias."""
        sources = [
            _make_source("alsa_input.usb-mic", "USB Microphone"),
            _make_source("bluez_input.AA:BB:CC:DD:EE:FF", "(null)",
                         extra_props={"bluez.alias": "AirPods Pro"}),
        ]
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sources"): (json.dumps(sources), 0),
        })
        scanner = StreamScanner()
        result = scanner.get_mic_sources()
        bt_src = [s for s in result if "bluez" in s["name"]][0]
        self.assertEqual(bt_src["description"], "AirPods Pro")

    @patch("subprocess.run")
    def test_bluez_source_empty_description_resolved(self, mock_run):
        """BlueZ sources with empty description should fall back through properties."""
        sources = [
            _make_source("bluez_input.AA:BB:CC:DD:EE:FF", "",
                         extra_props={"node.nick": "My Headset"}),
        ]
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sources"): (json.dumps(sources), 0),
        })
        scanner = StreamScanner()
        result = scanner.get_mic_sources()
        self.assertEqual(result[0]["description"], "My Headset")

    @patch("subprocess.run")
    def test_stream_with_empty_app_name_uses_node_name(self, mock_run):
        """Streams with empty app name should use node.name as process identity."""
        inputs = [
            _make_sink_input(248369, "", "Playback Stream", sink=0),
        ]
        mock_run.side_effect = _mock_subprocess_factory({
            ("pactl", "--format=json", "list", "sink-inputs"): (json.dumps(inputs), 0),
            ("pactl", "--format=json", "list", "sinks"): (json.dumps(SAMPLE_SINKS), 0),
        })
        scanner = StreamScanner()
        streams = scanner.get_app_streams()
        self.assertEqual(len(streams), 1)
        # node.name is set to "node_248369" by _make_sink_input fixture
        self.assertEqual(streams[0].display_name, "node_248369 — Playback Stream")


# ---------------------------------------------------------------------------
# AudioPipeline tests
# ---------------------------------------------------------------------------

class TestAudioPipeline(unittest.TestCase):

    @patch("subprocess.run")
    def test_setup_creates_combined_sink_and_mic_loopback(self, mock_run):
        calls_made = []

        def track_calls(args, **kwargs):
            calls_made.append(tuple(args))
            result = MagicMock()
            result.stdout = "42"  # Module ID
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = track_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")

        self.assertTrue(pipeline.is_active)

        # Verify null-sink creation
        null_sink_calls = [c for c in calls_made if "module-null-sink" in c]
        self.assertEqual(len(null_sink_calls), 1)
        self.assertIn(f"sink_name={COMBINED_SINK_NAME}", null_sink_calls[0])

        # Verify mic loopback
        loopback_calls = [c for c in calls_made if "module-loopback" in c]
        self.assertEqual(len(loopback_calls), 1)
        self.assertIn("source=alsa_input.usb-mic", loopback_calls[0])
        self.assertIn(f"sink={COMBINED_SINK_NAME}", loopback_calls[0])
        self.assertIn("source_dont_move=true", loopback_calls[0])
        self.assertIn("sink_dont_move=true", loopback_calls[0])

    @patch("subprocess.run")
    def test_add_app_creates_intermediate_sink_and_two_loopbacks(self, mock_run):
        module_counter = [0]
        calls_made = []

        def track_calls(args, **kwargs):
            calls_made.append(tuple(args))
            module_counter[0] += 1
            result = MagicMock()
            result.stdout = str(module_counter[0])
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = track_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")
        calls_made.clear()

        pipeline.add_app(100, "alsa_output.usb-speakers")

        # Should create: 1 null-sink + move-sink-input + 2 loopbacks = 4 commands
        null_sink_calls = [c for c in calls_made if "module-null-sink" in c]
        self.assertEqual(len(null_sink_calls), 1)
        self.assertIn(f"sink_name={APP_CAPTURE_PREFIX}100", null_sink_calls[0])

        move_calls = [c for c in calls_made if "move-sink-input" in c]
        self.assertEqual(len(move_calls), 1)
        self.assertIn("100", move_calls[0])
        self.assertIn(f"{APP_CAPTURE_PREFIX}100", move_calls[0])

        loopback_calls = [c for c in calls_made if "module-loopback" in c]
        self.assertEqual(len(loopback_calls), 2)

        # First loopback: intermediate -> original speakers
        speaker_lb = loopback_calls[0]
        self.assertIn(f"source={APP_CAPTURE_PREFIX}100.monitor", speaker_lb)
        self.assertIn("sink=alsa_output.usb-speakers", speaker_lb)

        # Second loopback: intermediate -> combined_mic
        combined_lb = loopback_calls[1]
        self.assertIn(f"source={APP_CAPTURE_PREFIX}100.monitor", combined_lb)
        self.assertIn(f"sink={COMBINED_SINK_NAME}", combined_lb)

    @patch("subprocess.run")
    def test_remove_app_restores_stream_and_unloads_modules(self, mock_run):
        module_counter = [0]
        calls_made = []

        def track_calls(args, **kwargs):
            module_counter[0] += 1
            result = MagicMock()
            result.stdout = str(module_counter[0])
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = track_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")
        pipeline.add_app(100, "alsa_output.usb-speakers")

        calls_made.clear()
        mock_run.side_effect = track_calls  # Reset

        pipeline.remove_app(100)

        # Collect calls after remove
        call_args = [tuple(c.args[0]) if hasattr(c, 'args') else () for c in mock_run.call_args_list]

        # Should have move-sink-input to restore + 3 unload-module calls
        # (intermediate sink + 2 loopbacks)
        restore_calls = [c for c in call_args if "move-sink-input" in c]
        self.assertTrue(len(restore_calls) >= 1)

        unload_calls = [c for c in call_args if "unload-module" in c]
        self.assertEqual(len(unload_calls), 3)  # 2 loopbacks + 1 null-sink

    @patch("subprocess.run")
    def test_teardown_cleans_up_everything(self, mock_run):
        module_counter = [0]

        def track_calls(args, **kwargs):
            module_counter[0] += 1
            result = MagicMock()
            result.stdout = str(module_counter[0])
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = track_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")
        pipeline.add_app(100, "alsa_output.usb-speakers")
        pipeline.add_app(101, "alsa_output.usb-speakers")

        self.assertTrue(pipeline.is_active)
        self.assertEqual(len(pipeline.captured_stream_indices), 2)

        mock_run.reset_mock()
        mock_run.side_effect = track_calls

        pipeline.teardown()

        self.assertFalse(pipeline.is_active)
        self.assertEqual(len(pipeline.captured_stream_indices), 0)

        # Verify unload-module calls were made (2 apps * 3 modules + mic loopback + combined sink)
        call_args = [tuple(c.args[0]) for c in mock_run.call_args_list]
        unload_calls = [c for c in call_args if "unload-module" in c]
        self.assertEqual(len(unload_calls), 8)  # 2*(2 loopbacks + 1 sink) + mic_lb + combined_sink

    @patch("subprocess.run")
    def test_teardown_is_idempotent(self, mock_run):
        module_counter = [0]

        def track_calls(args, **kwargs):
            module_counter[0] += 1
            result = MagicMock()
            result.stdout = str(module_counter[0])
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = track_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")
        pipeline.teardown()

        mock_run.reset_mock()

        # Second teardown should be a no-op
        pipeline.teardown()
        self.assertFalse(pipeline.is_active)
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_detect_disappeared_streams(self, mock_run):
        module_counter = [0]

        def setup_calls(args, **kwargs):
            module_counter[0] += 1
            result = MagicMock()
            result.stdout = str(module_counter[0])
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = setup_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")
        pipeline.add_app(100, "alsa_output.usb-speakers")
        pipeline.add_app(101, "alsa_output.usb-speakers")

        # Now mock stream_exists: stream 100 gone, 101 still there
        def detect_calls(args, **kwargs):
            key = tuple(args)
            if key == ("pactl", "--format=json", "list", "sink-inputs"):
                result = MagicMock()
                result.stdout = json.dumps([_make_sink_input(101, "Firefox")])
                result.stderr = ""
                result.returncode = 0
                return result
            # Default for unload operations
            result = MagicMock()
            result.stdout = ""
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = detect_calls

        disappeared = pipeline.detect_disappeared_streams()
        self.assertIn(100, disappeared)
        self.assertNotIn(101, disappeared)
        self.assertNotIn(100, pipeline.captured_stream_indices)
        self.assertIn(101, pipeline.captured_stream_indices)

    @patch("subprocess.run")
    def test_add_app_idempotent(self, mock_run):
        """Adding the same stream twice should be a no-op."""
        module_counter = [0]

        def track_calls(args, **kwargs):
            module_counter[0] += 1
            result = MagicMock()
            result.stdout = str(module_counter[0])
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = track_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")

        mock_run.reset_mock()
        mock_run.side_effect = track_calls

        pipeline.add_app(100, "alsa_output.usb-speakers")
        first_call_count = mock_run.call_count

        pipeline.add_app(100, "alsa_output.usb-speakers")
        # No additional calls should be made
        self.assertEqual(mock_run.call_count, first_call_count)

    @patch("subprocess.run")
    def test_setup_without_active_raises_on_add(self, mock_run):
        """add_app should raise if pipeline not set up."""
        pipeline = AudioPipeline()
        with self.assertRaises(RuntimeError):
            pipeline.add_app(100, "alsa_output.usb-speakers")

    @patch("subprocess.run")
    def test_remove_nonexistent_stream_is_noop(self, mock_run):
        """remove_app for unknown stream should not error."""
        module_counter = [0]

        def track_calls(args, **kwargs):
            module_counter[0] += 1
            result = MagicMock()
            result.stdout = str(module_counter[0])
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = track_calls

        pipeline = AudioPipeline()
        pipeline.setup("alsa_input.usb-mic")

        mock_run.reset_mock()

        # Should not raise or call anything
        pipeline.remove_app(999)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
