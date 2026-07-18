"""Tests for the AirPods AAP battery packet parser (pure logic).

The live L2CAP read requires the AirPods hardware and is verified manually against
a real device; these tests cover the packet parsing and level/status derivation.
`battery_reader` does not import PyQt6, so it is safe to import directly here.
"""
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

import battery_reader as br


class TestParseAapBattery(unittest.TestCase):
    def test_worked_example(self):
        # From the AAP docs: count=3, Right 100 discharging, Left 99 charging,
        # Case 17 discharging.
        pkt = bytes.fromhex("04000400040003" "0201640201" "0401630101" "0801110201")
        pods = br._parse_aap_battery(pkt)
        self.assertEqual(pods, {
            "right": (100, False), "left": (99, True), "case": (17, False),
        })

    def test_disconnected_component_dropped(self):
        # Right 90 discharging, Left 91 discharging, Case 0 disconnected (status 0x04).
        pkt = bytes.fromhex("04000400040003" "02015a0201" "04015b0201" "0801000401")
        pods = br._parse_aap_battery(pkt)
        self.assertEqual(pods, {"right": (90, False), "left": (91, False)})

    def test_bad_spacer_or_terminator_rejected(self):
        # rec[1] must be 0x01 and rec[4] must be 0x01; corrupt both records.
        pkt = bytes.fromhex("04000400040002" "0200640200" "04ff630100")
        self.assertEqual(br._parse_aap_battery(pkt), {})

    def test_non_battery_packet_ignored(self):
        self.assertEqual(br._parse_aap_battery(bytes.fromhex("0100040000")), {})
        self.assertEqual(br._parse_aap_battery(b""), {})

    def test_level_out_of_range_skipped(self):
        # level 0xFF (255) is out of the 0-100 range and must be dropped.
        pkt = bytes.fromhex("04000400040001" "0201ff0201")
        self.assertEqual(br._parse_aap_battery(pkt), {})


class TestAapPodsToInfo(unittest.TestCase):
    def test_level_is_min_of_ears_and_charging_if_any(self):
        info = br._aap_pods_to_info("AA:BB", {
            "right": (100, False), "left": (99, True), "case": (17, False),
        })
        self.assertEqual(info.level, 99)              # min(left, right)
        self.assertEqual(info.status, "Charging")     # left is charging
        self.assertEqual(info.details, {"left": 99, "right": 100, "case": 17})
        self.assertEqual(info.ids, {"mac": "AA:BB"})

    def test_discharging_when_no_pod_charging(self):
        info = br._aap_pods_to_info("AA:BB", {"right": (90, False), "left": (91, False)})
        self.assertEqual(info.level, 90)
        self.assertEqual(info.status, "Discharging")
        self.assertEqual(info.details, {"left": 91, "right": 90})

    def test_case_only_uses_case_level(self):
        info = br._aap_pods_to_info("AA:BB", {"case": (55, False)})
        self.assertEqual(info.level, 55)
        self.assertEqual(info.details, {"case": 55})

    def test_empty_pods_returns_none(self):
        self.assertIsNone(br._aap_pods_to_info("AA:BB", {}))


if __name__ == "__main__":
    unittest.main()
