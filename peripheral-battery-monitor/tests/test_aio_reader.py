"""Spec 017: aio_reader parsing and degradation.

Fixtures are trimmed captures of the live OpenLinkHub 0.9.1 API on njv-cachyos
(2026-09-06), including the "cluster" pseudo-device the daemon reports alongside
real hardware.
"""

import json
import os
import subprocess
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

import aio_reader  # noqa: E402


CPU_TEMP_FIXTURE = {"code": 200, "status": 1, "data": "98.0 °C"}

# Note `status: 0` — /api/devices/ reports success as 0, unlike /api/cpuTemp.
DEVICES_FIXTURE = {
    "code": 200,
    "status": 0,
    "devices": {
        "207132833748": {
            "Product": "iCUE COMMANDER Core",
            "Serial": "207132833748",
            "GetDevice": {
                "product": "iCUE COMMANDER Core",
                "serial": "207132833748",
                "firmware": "2.0.19",
                "devices": {
                    "0": {
                        "channelId": 0,
                        "deviceId": "AIO-0",
                        "name": "H150i ELITE LCD",
                        "rpm": 2399,
                        "temperature": 45.8,
                        "description": "AIO",
                        "HasSpeed": True,
                        "HasTemps": True,
                    },
                    "1": {
                        "channelId": 1,
                        "name": "Fan 1",
                        "rpm": 1469,
                        "temperature": 0,
                        "description": "Fan",
                        "HasSpeed": True,
                        "HasTemps": False,
                    },
                    "2": {
                        "channelId": 2,
                        "name": "Fan 2",
                        "rpm": 1462,
                        "temperature": 0,
                        "description": "Fan",
                        "HasSpeed": True,
                        "HasTemps": False,
                    },
                    "3": {
                        "channelId": 3,
                        "name": "Fan 3",
                        "rpm": 1451,
                        "temperature": 0,
                        "description": "Fan",
                        "HasSpeed": True,
                        "HasTemps": False,
                    },
                    "6": {
                        "channelId": 6,
                        "name": "Fan 6",
                        "rpm": 1238,
                        "temperature": 0,
                        "description": "Fan",
                        "HasSpeed": True,
                        "HasTemps": False,
                    },
                },
            },
        },
        # Pseudo-device: real in the API response, no channels.
        "cluster": {
            "Product": "Cluster",
            "Serial": "cluster",
            "GetDevice": {"product": "Cluster", "devices": {}},
        },
    },
}


def _devices_with(channels: dict) -> dict:
    return {
        "code": 200,
        "status": 0,
        "devices": {
            "serial": {
                "Product": "Test Device",
                "GetDevice": {"product": "Test Device", "devices": channels},
            }
        },
    }


class TestSnapshot(unittest.TestCase):
    def test_parses_live_fixture(self):
        """AC1: the captured live response yields every displayed metric."""
        snap = aio_reader.build_snapshot(CPU_TEMP_FIXTURE, DEVICES_FIXTURE)
        self.assertTrue(snap["available"])
        self.assertIsNone(snap["error"])
        self.assertEqual(snap["cpu_temp_c"], 98.0)
        self.assertEqual(snap["coolant_temp_c"], 45.8)
        self.assertEqual(snap["pump_rpm"], 2399)
        self.assertEqual(snap["coolant_label"], "H150i ELITE LCD")
        self.assertEqual(
            snap["fans"],
            [
                {"name": "Fan 1", "rpm": 1469},
                {"name": "Fan 2", "rpm": 1462},
                {"name": "Fan 3", "rpm": 1451},
                {"name": "Fan 6", "rpm": 1238},
            ],
        )

    def test_devices_status_zero_is_success(self):
        """AC2: /api/devices/ is gated on channels, never on status == 1."""
        self.assertEqual(DEVICES_FIXTURE["status"], 0)
        snap = aio_reader.build_snapshot(None, DEVICES_FIXTURE)
        self.assertTrue(snap["available"])
        self.assertEqual(snap["coolant_temp_c"], 45.8)

    def test_cluster_pseudo_device_skipped(self):
        """AC3: a device with no channels contributes nothing."""
        only_cluster = {
            "code": 200,
            "status": 0,
            "devices": {"cluster": DEVICES_FIXTURE["devices"]["cluster"]},
        }
        snap = aio_reader.build_snapshot(None, only_cluster)
        self.assertFalse(snap["available"])
        self.assertEqual(snap["fans"], [])

    def test_snapshot_is_json_serializable(self):
        json.dumps(aio_reader.build_snapshot(CPU_TEMP_FIXTURE, DEVICES_FIXTURE))

    def test_unreachable_daemon(self):
        """AC5: both responses missing degrades without raising."""
        snap = aio_reader.build_snapshot(None, None)
        self.assertFalse(snap["available"])
        self.assertTrue(snap["error"])
        self.assertIsNone(snap["cpu_temp_c"])
        self.assertEqual(snap["fans"], [])

    def test_no_supported_device(self):
        """AC6: a daemon managing only unsupported hardware is unavailable."""
        devices = _devices_with(
            {
                "0": {
                    "name": "MM700 Mousepad",
                    "rpm": 0,
                    "temperature": 0,
                    "description": "LED",
                    "HasSpeed": False,
                    "HasTemps": False,
                }
            }
        )
        snap = aio_reader.build_snapshot({"status": 0}, devices)
        self.assertFalse(snap["available"])
        self.assertEqual(snap["error"], "no supported device")

    def test_fans_without_aio_channel(self):
        """AC7: a fan controller with no cooler still reports fans."""
        devices = _devices_with(
            {
                "0": {
                    "name": "Fan 1",
                    "rpm": 900,
                    "temperature": 0,
                    "description": "Fan",
                    "HasSpeed": True,
                    "HasTemps": False,
                }
            }
        )
        snap = aio_reader.build_snapshot(None, devices)
        self.assertTrue(snap["available"])
        self.assertIsNone(snap["coolant_temp_c"])
        self.assertIsNone(snap["pump_rpm"])
        self.assertEqual(snap["fans"], [{"name": "Fan 1", "rpm": 900}])

    def test_temperature_probe_fallback(self):
        """A cooler that does not use the "AIO" description is still found."""
        devices = _devices_with(
            {
                "0": {
                    "name": "Water Block",
                    "rpm": 1800,
                    "temperature": 33.5,
                    "description": "Pump",
                    "HasSpeed": True,
                    "HasTemps": True,
                }
            }
        )
        snap = aio_reader.build_snapshot(None, devices)
        self.assertEqual(snap["coolant_temp_c"], 33.5)
        self.assertEqual(snap["pump_rpm"], 1800)
        self.assertEqual(snap["coolant_label"], "Water Block")

    def test_zero_temperature_is_not_a_reading(self):
        """OpenLinkHub uses 0 as the null temperature on fan channels."""
        devices = _devices_with(
            {
                "0": {
                    "name": "AIO",
                    "rpm": 2000,
                    "temperature": 0,
                    "description": "AIO",
                    "HasSpeed": True,
                    "HasTemps": True,
                }
            }
        )
        snap = aio_reader.build_snapshot(None, devices)
        self.assertIsNone(snap["coolant_temp_c"])
        self.assertEqual(snap["pump_rpm"], 2000)


class TestTemperatureParsing(unittest.TestCase):
    """AC4: every temperature representation the daemon can emit."""

    def test_celsius_string(self):
        self.assertEqual(aio_reader._parse_temperature("98.0 °C"), 98.0)

    def test_fahrenheit_string_converts(self):
        self.assertEqual(aio_reader._parse_temperature("208.4 °F"), 98.0)

    def test_bare_number_string(self):
        self.assertEqual(aio_reader._parse_temperature("98"), 98.0)

    def test_numeric(self):
        self.assertEqual(aio_reader._parse_temperature(45.8), 45.8)

    def test_empty_and_none(self):
        self.assertIsNone(aio_reader._parse_temperature(""))
        self.assertIsNone(aio_reader._parse_temperature("   "))
        self.assertIsNone(aio_reader._parse_temperature(None))

    def test_garbage(self):
        self.assertIsNone(aio_reader._parse_temperature("n/a"))
        self.assertIsNone(aio_reader._parse_temperature({"c": 1}))

    def test_cpu_temp_requires_status_one(self):
        self.assertIsNone(aio_reader._extract_cpu_temp({"status": 0, "data": "98.0 °C"}))
        self.assertEqual(aio_reader._extract_cpu_temp(CPU_TEMP_FIXTURE), 98.0)


class TestFanAverage(unittest.TestCase):
    def test_excludes_stopped_fans_but_keeps_them_listed(self):
        """AC8: a zero-RPM fan is a real state, not a broken reading."""
        devices = _devices_with(
            {
                "0": {
                    "name": "Fan 1",
                    "rpm": 1000,
                    "description": "Fan",
                    "HasSpeed": True,
                },
                "1": {
                    "name": "Fan 2",
                    "rpm": 0,
                    "description": "Fan",
                    "HasSpeed": True,
                },
                "2": {
                    "name": "Fan 3",
                    "rpm": 1200,
                    "description": "Fan",
                    "HasSpeed": True,
                },
            }
        )
        snap = aio_reader.build_snapshot(None, devices)
        self.assertEqual(len(snap["fans"]), 3)
        self.assertEqual(aio_reader.average_fan_rpm(snap["fans"]), 1100)

    def test_no_spinning_fans(self):
        self.assertIsNone(aio_reader.average_fan_rpm([{"name": "Fan 1", "rpm": 0}]))
        self.assertIsNone(aio_reader.average_fan_rpm([]))


class TestMalformedResponses(unittest.TestCase):
    """The daemon's shape has already drifted once between releases; every
    field is treated as optional."""

    def test_shapes_that_must_not_raise(self):
        for payload in (
            {},
            {"devices": None},
            {"devices": {}},
            {"devices": {"s": None}},
            {"devices": {"s": {"GetDevice": None}}},
            {"devices": {"s": {"GetDevice": {"devices": None}}}},
            {"devices": {"s": {"GetDevice": {"devices": {"0": "not-a-dict"}}}}},
            {"devices": {"s": {"GetDevice": {"devices": {"0": {}}}}}},
            "a string",
            [],
        ):
            with self.subTest(payload=payload):
                snap = aio_reader.build_snapshot(None, payload)
                self.assertFalse(snap["available"])


class TestEndpointsAndDecoding(unittest.TestCase):
    def test_endpoint_urls(self):
        urls = aio_reader.endpoint_urls("http://127.0.0.1:27003/api/")
        self.assertEqual(urls["cpu"], "http://127.0.0.1:27003/api/cpuTemp")
        self.assertEqual(urls["devices"], "http://127.0.0.1:27003/api/devices/")

    def test_endpoint_keys_match_build_snapshot_arguments(self):
        self.assertEqual(set(aio_reader.endpoint_urls()), {"cpu", "devices"})

    def test_decode_payload(self):
        self.assertEqual(aio_reader.decode_payload(b'{"a": 1}'), {"a": 1})
        self.assertEqual(aio_reader.decode_payload('{"a": 1}'), {"a": 1})

    def test_decode_payload_rejects_junk(self):
        for raw in (b"", None, b"not json", b"\xff\xfe"):
            with self.subTest(raw=raw):
                self.assertIsNone(aio_reader.decode_payload(raw))

    def test_channel_order_is_numeric(self):
        """Channel "10" must sort after "9", not between "1" and "2"."""
        channels = {
            str(i): {
                "name": f"Fan {i}",
                "rpm": 1000 + i,
                "description": "Fan",
                "HasSpeed": True,
            }
            for i in (1, 2, 9, 10)
        }
        snap = aio_reader.build_snapshot(None, _devices_with(channels))
        self.assertEqual([f["name"] for f in snap["fans"]],
                         ["Fan 1", "Fan 2", "Fan 9", "Fan 10"])


class TestCli(unittest.TestCase):
    def test_json_output_without_a_daemon(self):
        """AC9: the CLI prints valid JSON and exits 0 even with nothing to talk to."""
        env = dict(os.environ)
        # Port 1 refuses instantly; no test should wait on a network timeout.
        env["OPENLINKHUB_API"] = "http://127.0.0.1:1/api"
        proc = subprocess.run(
            [sys.executable, os.path.join(PROJECT_DIR, "aio_reader.py"), "--json"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snap = json.loads(proc.stdout)
        self.assertFalse(snap["available"])
        self.assertEqual(snap["error"], "openlinkhub unreachable")


class TestReadOnly(unittest.TestCase):
    def test_no_write_calls_in_new_modules(self):
        """AC18: fan/pump duty writes are silently discarded by this firmware,
        so the section must never issue one."""
        for name in ("aio_reader.py", "aio_section.py"):
            with self.subTest(module=name):
                source = open(os.path.join(PROJECT_DIR, name)).read()
                for forbidden in ('"POST"', "'POST'", ".post(", "setSpeed", "/api/speed"):
                    self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
