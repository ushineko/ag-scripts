"""Tests for bandwidth_reader (data layer) and bandwidth_section row math."""

import json
import os
import sys
import unittest
from unittest.mock import patch

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

# Force offscreen Qt so QLabel construction in _InterfaceRow doesn't need a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import bandwidth_reader
from PyQt6.QtWidgets import QApplication
import bandwidth_section


_app: QApplication | None = None


def _ensure_qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication(sys.argv)
    return _app


PROC_NET_DEV_FIXTURE = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 100 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0
  eno2: 5000 50 0 0 0 0 0 100 2000 20 0 0 0 0 0 0
tailscale0: 12345 100 0 0 0 0 0 0 67890 80 0 0 0 0 0 0
"""


class TestProcParser(unittest.TestCase):
    def test_parser_extracts_rx_and_tx(self):
        parsed = bandwidth_reader._parse_proc_net_dev(PROC_NET_DEV_FIXTURE)
        self.assertEqual(parsed["lo"]["rx_bytes"], 100)
        self.assertEqual(parsed["lo"]["tx_bytes"], 100)
        self.assertEqual(parsed["eno2"]["rx_bytes"], 5000)
        self.assertEqual(parsed["eno2"]["tx_bytes"], 2000)
        self.assertEqual(parsed["tailscale0"]["rx_bytes"], 12345)
        self.assertEqual(parsed["tailscale0"]["tx_bytes"], 67890)

    def test_parser_skips_malformed_lines(self):
        bad = "Inter-| garbage\n face | header\nfoobar without a colon\n"
        parsed = bandwidth_reader._parse_proc_net_dev(bad)
        self.assertEqual(parsed, {})


class TestReadInterfaces(unittest.TestCase):
    def test_known_interfaces_returns_counters(self):
        with patch.object(bandwidth_reader, "_read_proc_net_dev") as m:
            m.return_value = {
                "eno2": {"rx_bytes": 111, "tx_bytes": 222},
                "tailscale0": {"rx_bytes": 333, "tx_bytes": 444},
            }
            out = bandwidth_reader.read_interfaces(["eno2", "tailscale0"])
        self.assertEqual(len(out["interfaces"]), 2)
        eno = next(i for i in out["interfaces"] if i["name"] == "eno2")
        self.assertTrue(eno["exists"])
        self.assertEqual(eno["rx_bytes"], 111)
        self.assertEqual(eno["tx_bytes"], 222)
        self.assertIsNone(eno["metadata"])

    def test_missing_interface_reports_exists_false_zero_counters(self):
        with patch.object(bandwidth_reader, "_read_proc_net_dev") as m:
            m.return_value = {"eno2": {"rx_bytes": 5, "tx_bytes": 5}}
            out = bandwidth_reader.read_interfaces(["eno2", "ghost0"])
        ghost = next(i for i in out["interfaces"] if i["name"] == "ghost0")
        self.assertFalse(ghost["exists"])
        self.assertEqual(ghost["rx_bytes"], 0)
        self.assertEqual(ghost["tx_bytes"], 0)

    def test_json_roundtrip(self):
        with patch.object(bandwidth_reader, "_read_proc_net_dev") as m:
            m.return_value = {"lo": {"rx_bytes": 1, "tx_bytes": 2}}
            out = bandwidth_reader.read_interfaces(["lo"])
        # Must be JSON-serializable with stdlib only (no custom encoders).
        serialized = json.dumps(out)
        parsed = json.loads(serialized)
        self.assertEqual(parsed, out)


class TestTailscaleMetadata(unittest.TestCase):
    def test_status_unavailable_yields_unknown_metadata(self):
        with patch.object(bandwidth_reader, "_read_proc_net_dev") as m, \
             patch.object(bandwidth_reader, "_fetch_tailscale_status", return_value=None):
            m.return_value = {"tailscale0": {"rx_bytes": 1, "tx_bytes": 2}}
            # Bypass module-level cache so the test runs deterministically.
            bandwidth_reader._TS_META_CACHE = None
            bandwidth_reader._TS_META_CACHE_TS = 0.0
            out = bandwidth_reader.read_interfaces(
                ["tailscale0"], include_tailscale_meta=True
            )
        ts = out["interfaces"][0]["metadata"]
        self.assertEqual(ts["type"], "tailscale")
        self.assertEqual(ts["backend_state"], "unknown")
        self.assertIsNone(ts["exit_node"])
        self.assertIsNone(ts["exit_node_online"])

    def test_exit_node_hostname_extracted_from_peer_list(self):
        fake_status = {
            "BackendState": "Running",
            "ExitNodeStatus": {"ID": "abc123", "Online": True},
            "Peer": {
                "k1": {"ID": "xyz", "HostName": "irrelevant"},
                "k2": {"ID": "abc123", "HostName": "us-east-exit"},
            },
        }
        summary = bandwidth_reader._summarize_tailscale(fake_status)
        self.assertEqual(summary["backend_state"], "Running")
        self.assertEqual(summary["exit_node"], "us-east-exit")
        self.assertTrue(summary["exit_node_online"])

    def test_no_exit_node_returns_none(self):
        fake_status = {"BackendState": "Running", "Peer": {}}
        summary = bandwidth_reader._summarize_tailscale(fake_status)
        self.assertEqual(summary["backend_state"], "Running")
        self.assertIsNone(summary["exit_node"])
        self.assertIsNone(summary["exit_node_online"])


class TestRowRateMath(unittest.TestCase):
    """Pure-logic tests on _InterfaceRow.ingest_sample."""

    def setUp(self):
        _ensure_qapp()

    def test_first_sample_yields_zero_rate(self):
        row = bandwidth_section._InterfaceRow("eth0", 0, 0, parent=None)
        rx, tx = row.ingest_sample(True, 1000, 2000, ts=100.0)
        self.assertEqual(rx, 0.0)
        self.assertEqual(tx, 0.0)
        # Cumulative is unchanged on the very first sample.
        self.assertEqual(row.cumulative_rx, 0)
        self.assertEqual(row.cumulative_tx, 0)

    def test_two_samples_compute_per_second_rate_and_accumulate(self):
        row = bandwidth_section._InterfaceRow("eth0", 0, 0, parent=None)
        row.ingest_sample(True, 1000, 2000, ts=100.0)
        rx, tx = row.ingest_sample(True, 11000, 22000, ts=110.0)
        # 10_000 bytes over 10 seconds = 1000 B/s
        self.assertAlmostEqual(rx, 1000.0)
        # 20_000 bytes over 10 seconds = 2000 B/s
        self.assertAlmostEqual(tx, 2000.0)
        self.assertEqual(row.cumulative_rx, 10_000)
        self.assertEqual(row.cumulative_tx, 20_000)

    def test_counter_reset_yields_zero_rate_and_no_cumulative_change(self):
        row = bandwidth_section._InterfaceRow("eth0", 500, 500, parent=None)
        row.ingest_sample(True, 10_000, 10_000, ts=100.0)
        # Counter went backwards (interface re-created); should not produce
        # negative rates and should not subtract from cumulative.
        rx, tx = row.ingest_sample(True, 100, 100, ts=110.0)
        self.assertEqual(rx, 0.0)
        self.assertEqual(tx, 0.0)
        self.assertEqual(row.cumulative_rx, 500)
        self.assertEqual(row.cumulative_tx, 500)
        # Subsequent normal delta resumes from the re-anchored baseline.
        rx, tx = row.ingest_sample(True, 1100, 1100, ts=120.0)
        self.assertAlmostEqual(rx, 100.0)
        self.assertAlmostEqual(tx, 100.0)
        self.assertEqual(row.cumulative_rx, 1500)
        self.assertEqual(row.cumulative_tx, 1500)

    def test_missing_interface_resets_baseline(self):
        row = bandwidth_section._InterfaceRow("eth0", 0, 0, parent=None)
        row.ingest_sample(True, 1000, 1000, ts=100.0)
        # Interface disappears.
        rx, tx = row.ingest_sample(False, 0, 0, ts=110.0)
        self.assertEqual(rx, 0.0)
        self.assertEqual(tx, 0.0)
        self.assertIsNone(row.last_raw_rx)
        # Interface reappears with high counters; first sample after reappearance
        # must not be treated as a delta from before-disappearance.
        rx, tx = row.ingest_sample(True, 999_999, 999_999, ts=120.0)
        self.assertEqual(rx, 0.0)
        self.assertEqual(tx, 0.0)
        self.assertEqual(row.cumulative_rx, 0)
        self.assertEqual(row.cumulative_tx, 0)


class TestRowFormatting(unittest.TestCase):
    """Quick checks on the human-readable formatting helpers."""

    def test_format_bytes_basic_units(self):
        # Number column right-aligned to 5 chars; unit column left-aligned to 3 chars.
        self.assertEqual(bandwidth_section._format_bytes(0), "    0 B  ")
        self.assertEqual(bandwidth_section._format_bytes(512), "  512 B  ")
        self.assertEqual(bandwidth_section._format_bytes(1024), "  1.0 KiB")
        self.assertEqual(bandwidth_section._format_bytes(1024 * 1024), "  1.0 MiB")

    def test_format_bytes_fixed_width_across_unit_transitions(self):
        # All outputs must share the same total length so column alignment is stable.
        widths = {
            len(bandwidth_section._format_bytes(v))
            for v in (0, 512, 1023, 1024, 1024 * 1024, 1024 * 1024 * 1024)
        }
        self.assertEqual(len(widths), 1, f"widths varied: {widths}")

    def test_format_rate_fixed_width_and_per_second_suffix(self):
        rate_str = bandwidth_section._format_rate(2048)
        self.assertTrue("/s" in rate_str)
        # Rate strings (which add the /s suffix) all share one width.
        widths = {
            len(bandwidth_section._format_rate(v))
            for v in (0, 999, 1024, 1024 * 1024 * 1024)
        }
        self.assertEqual(len(widths), 1, f"rate widths varied: {widths}")


class TestMetadataSubtitle(unittest.TestCase):
    def test_exit_node_subtitle(self):
        sub = bandwidth_section.BandwidthSection._format_metadata({
            "type": "tailscale", "backend_state": "Running",
            "exit_node": "us-east", "exit_node_online": True,
        })
        self.assertEqual(sub, "exit: us-east")

    def test_exit_node_offline_subtitle(self):
        sub = bandwidth_section.BandwidthSection._format_metadata({
            "type": "tailscale", "backend_state": "Running",
            "exit_node": "us-east", "exit_node_online": False,
        })
        self.assertEqual(sub, "exit: us-east (offline)")

    def test_no_exit_node_running_returns_none(self):
        sub = bandwidth_section.BandwidthSection._format_metadata({
            "type": "tailscale", "backend_state": "Running",
            "exit_node": None, "exit_node_online": None,
        })
        self.assertIsNone(sub)

    def test_non_running_backend_surfaces_state(self):
        sub = bandwidth_section.BandwidthSection._format_metadata({
            "type": "tailscale", "backend_state": "NeedsLogin",
            "exit_node": None, "exit_node_online": None,
        })
        self.assertEqual(sub, "tailscale: NeedsLogin")


if __name__ == "__main__":
    unittest.main()
