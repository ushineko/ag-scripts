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


class TestRgbTarget(unittest.TestCase):
    """Spec 019: the RGB write target, discovered from `rgbDevices`."""

    @staticmethod
    def _device(*, serial, aio=False, rgb_channels=(), brightness=None):
        detail = {
            "product": "Test Device",
            "serial": serial,
            "devices": {},
            "rgbDevices": {
                str(c): {"channelId": c, "description": "LED"} for c in rgb_channels
            },
        }
        if aio:
            detail["devices"] = {
                "0": {
                    "name": "Cooler",
                    "rpm": 2000,
                    "temperature": 45.0,
                    "description": "AIO",
                    "HasSpeed": True,
                    "HasTemps": True,
                }
            }
        if brightness is not None:
            detail["DeviceProfile"] = {"Brightness": brightness}
        return detail

    def _payload(self, *details):
        return {
            "code": 200,
            "status": 0,
            "devices": {d["serial"]: {"GetDevice": d} for d in details},
        }

    def test_live_fixture(self):
        """AC1: against the captured response, with rgbDevices attached."""
        payload = json.loads(json.dumps(DEVICES_FIXTURE))
        detail = payload["devices"]["207132833748"]["GetDevice"]
        detail["rgbDevices"] = {str(c): {"channelId": c} for c in range(7)}
        detail["DeviceProfile"] = {"Brightness": 3}
        snap = aio_reader.build_snapshot(CPU_TEMP_FIXTURE, payload)
        self.assertEqual(snap["device_id"], "207132833748")
        self.assertEqual(snap["rgb_channels"], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(snap["brightness"], 3)

    def test_prefers_the_device_owning_the_aio_channel(self):
        """AC2: not merely the first device with RGB."""
        payload = self._payload(
            self._device(serial="mousepad", rgb_channels=(0,)),
            self._device(serial="cooler", aio=True, rgb_channels=(0, 1, 2), brightness=2),
        )
        snap = aio_reader.build_snapshot(None, payload)
        self.assertEqual(snap["device_id"], "cooler")
        self.assertEqual(snap["rgb_channels"], [0, 1, 2])
        self.assertEqual(snap["brightness"], 2)

    def test_falls_back_to_the_first_rgb_device(self):
        payload = self._payload(
            self._device(serial="mousepad", rgb_channels=(0, 1)),
            self._device(serial="strip", rgb_channels=(0,)),
        )
        snap = aio_reader.build_snapshot(None, payload)
        self.assertEqual(snap["device_id"], "mousepad")
        self.assertEqual(snap["rgb_channels"], [0, 1])

    def test_no_rgb_anywhere(self):
        payload = self._payload(self._device(serial="fanhub", aio=True))
        snap = aio_reader.build_snapshot(None, payload)
        self.assertIsNone(snap["device_id"])
        self.assertEqual(snap["rgb_channels"], [])
        self.assertIsNone(snap["brightness"])

    def test_channels_are_numerically_sorted(self):
        payload = self._payload(
            self._device(serial="strip", rgb_channels=(0, 1, 2, 9, 10, 11))
        )
        snap = aio_reader.build_snapshot(None, payload)
        self.assertEqual(snap["rgb_channels"], [0, 1, 2, 9, 10, 11])

    def test_missing_brightness_is_none(self):
        payload = self._payload(self._device(serial="strip", rgb_channels=(0,)))
        self.assertIsNone(aio_reader.build_snapshot(None, payload)["brightness"])

    def test_unreachable_daemon_has_no_target(self):
        snap = aio_reader.build_snapshot(None, None)
        self.assertIsNone(snap["device_id"])
        self.assertEqual(snap["rgb_channels"], [])


class TestEndpointsAndDecoding(unittest.TestCase):
    def test_endpoint_urls(self):
        urls = aio_reader.endpoint_urls("http://127.0.0.1:27003/api/")
        self.assertEqual(urls["cpu"], "http://127.0.0.1:27003/api/cpuTemp")
        self.assertEqual(urls["devices"], "http://127.0.0.1:27003/api/devices/")

    def test_endpoint_keys_match_build_snapshot_arguments(self):
        self.assertEqual(set(aio_reader.endpoint_urls()), {"cpu", "gpu", "devices"})

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
        """AC9: the CLI prints valid JSON and exits 0 even with nothing to talk to.

        Spec 020 isolates liquidctl as well. Before it, pointing only
        OPENLINKHUB_API at a dead port was enough to starve the reader; liquidctl
        is now an independent source, so a real cooler still answers.
        """
        env = dict(os.environ)
        # Port 1 refuses instantly; no test should wait on a network timeout.
        env["OPENLINKHUB_API"] = "http://127.0.0.1:1/api"
        env["LIQUIDCTL_BIN"] = "liquidctl-does-not-exist"
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
        self.assertEqual(snap["error"], "no cooling source reachable")

    def test_json_output_with_only_liquidctl(self):
        """020 AC12: liquidctl alone is enough; OpenLinkHub may be absent."""
        if not aio_reader.liquidctl_available():
            self.skipTest("liquidctl not installed")
        env = dict(os.environ)
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
        # No cooler attached in CI is legitimate; assert only that a cooler
        # reading, when present, is attributed to liquidctl and never to the
        # unreachable daemon.
        if snap["available"]:
            self.assertIn(snap["cooler_source"], ("liquidctl", None))
            self.assertIsNone(snap["cpu_temp_c"])


class TestNoSpeedWrites(unittest.TestCase):
    """019 AC12, superseding 017 AC18.

    The reader itself still issues no write of any kind; the narrowed guard
    against speed endpoints applies to every AIO module.
    """

    SPEED_ENDPOINTS = (
        "/api/speed",
        "/api/psu/speed",
        "/api/temperatures/new",
        "/api/temperatures/update",
        "/api/temperatures/updateGraph",
        "setSpeed",
    )

    def test_no_speed_write_path(self):
        for name in ("aio_reader.py", "aio_section.py", "aio_color.py"):
            source = open(os.path.join(PROJECT_DIR, name)).read()
            for endpoint in self.SPEED_ENDPOINTS:
                with self.subTest(module=name, endpoint=endpoint):
                    self.assertNotIn(endpoint, source)

    def test_reader_issues_no_writes(self):
        source = open(os.path.join(PROJECT_DIR, "aio_reader.py")).read()
        for forbidden in ('"POST"', "'POST'", "method=", ".post("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Spec 020: liquidctl source, PSU-probe exclusion, and pump alerting.
# ---------------------------------------------------------------------------

# Trimmed capture of `liquidctl --json --match kraken status` on njv-cachyos
# (2026-09-16), NZXT Kraken Elite V2 (1e71:3012).
LIQUIDCTL_FIXTURE = [
    {
        "bus": "hid",
        "address": "/dev/hidraw14",
        "description": "NZXT Kraken 2024 Elite RGB",
        "status": [
            {"key": "Liquid temperature", "value": 36.3, "unit": "°C"},
            {"key": "Pump speed", "value": 1735, "unit": "rpm"},
            {"key": "Pump duty", "value": 35, "unit": "%"},
            {"key": "Fan speed", "value": 840, "unit": "rpm"},
            {"key": "Fan duty", "value": 35, "unit": "%"},
        ],
    }
]

# The HX1000i as OpenLinkHub actually reports it. These "Probe" channels are the
# ones that previously masqueraded as coolant.
PSU_ONLY_DEVICES = {
    "code": 200,
    "status": 0,
    "devices": {
        "c19b64": {
            "Product": "HX1000i",
            "Serial": "c19b64",
            "GetDevice": {
                "product": "HX1000i",
                "serial": "c19b64",
                "devices": {
                    "1": {"name": "Fan 1", "description": "", "temperature": 0,
                          "rpm": 0, "HasSpeed": True, "HasTemps": False},
                    "2": {"name": "VRM Temperature", "description": "Probe",
                          "temperature": 45.25, "rpm": 0,
                          "HasSpeed": False, "HasTemps": True},
                    "3": {"name": "PSU Temperature", "description": "Probe",
                          "temperature": 45.25, "rpm": 0,
                          "HasSpeed": False, "HasTemps": True},
                },
            },
        }
    },
}


class TestLiquidctlParsing(unittest.TestCase):
    """020 AC1."""

    def test_parses_live_fixture(self):
        cooler = aio_reader.parse_liquidctl(LIQUIDCTL_FIXTURE)
        self.assertEqual(cooler["coolant_temp_c"], 36.3)
        self.assertEqual(cooler["pump_rpm"], 1735)
        self.assertEqual(cooler["label"], "NZXT Kraken 2024 Elite RGB")
        self.assertEqual([f["rpm"] for f in cooler["fans"]], [840])

    def test_accepts_raw_json_text(self):
        cooler = aio_reader.parse_liquidctl(json.dumps(LIQUIDCTL_FIXTURE))
        self.assertEqual(cooler["pump_rpm"], 1735)

    def test_accepts_bytes(self):
        cooler = aio_reader.parse_liquidctl(json.dumps(LIQUIDCTL_FIXTURE).encode())
        self.assertEqual(cooler["pump_rpm"], 1735)

    def test_unusable_input_is_none(self):
        for bad in (None, b"", "", "not json", {}, [], [{"status": "nope"}]):
            with self.subTest(bad=bad):
                self.assertIsNone(aio_reader.parse_liquidctl(bad))

    def test_device_without_cooler_metrics_is_skipped(self):
        """A PSU that liquidctl can read is not a cooler."""
        payload = [{"description": "Corsair HX1000i",
                    "status": [{"key": "Total power", "value": 120, "unit": "W"}]}]
        self.assertIsNone(aio_reader.parse_liquidctl(payload))

    def test_pump_without_temperature_still_counts(self):
        payload = [{"description": "Pump only",
                    "status": [{"key": "Pump speed", "value": 1200, "unit": "rpm"}]}]
        cooler = aio_reader.parse_liquidctl(payload)
        self.assertEqual(cooler["pump_rpm"], 1200)
        self.assertIsNone(cooler["coolant_temp_c"])


class TestPsuProbeIsNotCoolant(unittest.TestCase):
    """020 AC3/AC4 — the regression that motivated the spec."""

    def test_psu_probes_are_not_reported_as_coolant(self):
        snap = aio_reader.build_snapshot(None, PSU_ONLY_DEVICES)
        self.assertIsNone(snap["coolant_temp_c"])
        self.assertIsNone(snap["coolant_label"])
        self.assertIsNone(snap["cooler_source"])

    def test_psu_probes_do_not_fake_a_stopped_pump(self):
        """The old fallback produced pump_rpm 0, which reads as a dead pump."""
        snap = aio_reader.build_snapshot(None, PSU_ONLY_DEVICES)
        self.assertIsNone(snap["pump_rpm"])
        self.assertEqual(snap["alert_state"], aio_reader.ALERT_OK)

    def test_genuine_cooler_descriptions_still_accepted(self):
        for description in ("Pump", "Water Block", "Liquid"):
            with self.subTest(description=description):
                devices = _devices_with({
                    "0": {"name": "Block", "rpm": 1800, "temperature": 33.5,
                          "description": description,
                          "HasSpeed": True, "HasTemps": True},
                })
                snap = aio_reader.build_snapshot(None, devices)
                self.assertEqual(snap["coolant_temp_c"], 33.5)
                self.assertEqual(snap["pump_rpm"], 1800)
                self.assertEqual(snap["cooler_source"], "openlinkhub")


class TestSourcePrecedence(unittest.TestCase):
    """020 AC2 and AC11."""

    def test_liquidctl_wins_over_openlinkhub(self):
        devices = _devices_with({
            "0": {"name": "AIO", "rpm": 2000, "temperature": 99.0,
                  "description": "AIO", "HasSpeed": True, "HasTemps": True},
        })
        snap = aio_reader.build_snapshot(None, devices, LIQUIDCTL_FIXTURE)
        self.assertEqual(snap["coolant_temp_c"], 36.3)
        self.assertEqual(snap["pump_rpm"], 1735)
        self.assertEqual(snap["cooler_source"], "liquidctl")

    def test_openlinkhub_used_when_liquidctl_absent(self):
        devices = _devices_with({
            "0": {"name": "AIO", "rpm": 2000, "temperature": 41.0,
                  "description": "AIO", "HasSpeed": True, "HasTemps": True},
        })
        snap = aio_reader.build_snapshot(None, devices, None)
        self.assertEqual(snap["coolant_temp_c"], 41.0)
        self.assertEqual(snap["cooler_source"], "openlinkhub")

    def test_cpu_temp_still_comes_from_openlinkhub(self):
        snap = aio_reader.build_snapshot(CPU_TEMP_FIXTURE, None, LIQUIDCTL_FIXTURE)
        self.assertEqual(snap["cpu_temp_c"], 98.0)
        self.assertEqual(snap["cooler_source"], "liquidctl")

    def test_liquidctl_alone_is_available(self):
        snap = aio_reader.build_snapshot(None, None, LIQUIDCTL_FIXTURE)
        self.assertTrue(snap["available"])
        self.assertIsNone(snap["error"])

    def test_no_source_at_all(self):
        snap = aio_reader.build_snapshot(None, None, None)
        self.assertFalse(snap["available"])
        self.assertEqual(snap["error"], "no cooling source reachable")

    def test_snapshot_is_json_serializable(self):
        snap = aio_reader.build_snapshot(CPU_TEMP_FIXTURE, PSU_ONLY_DEVICES,
                                         LIQUIDCTL_FIXTURE)
        json.dumps(snap)


class TestAlertEvaluation(unittest.TestCase):
    """020 AC6 and AC13."""

    def _snap(self, **kw):
        base = {"pump_rpm": 1700, "coolant_temp_c": 36.0}
        base.update(kw)
        return base

    def test_healthy_is_ok(self):
        state, reason = aio_reader.evaluate_alert(self._snap())
        self.assertEqual(state, aio_reader.ALERT_OK)
        self.assertIsNone(reason)

    def test_stopped_pump_is_critical(self):
        state, reason = aio_reader.evaluate_alert(self._snap(pump_rpm=0))
        self.assertEqual(state, aio_reader.ALERT_CRITICAL)
        self.assertIn("Pump stopped", reason)

    def test_hot_coolant_is_critical(self):
        state, reason = aio_reader.evaluate_alert(self._snap(coolant_temp_c=61.0))
        self.assertEqual(state, aio_reader.ALERT_CRITICAL)
        self.assertIn("Coolant", reason)

    def test_slow_pump_is_warning(self):
        state, reason = aio_reader.evaluate_alert(self._snap(pump_rpm=300))
        self.assertEqual(state, aio_reader.ALERT_WARNING)

    def test_warm_coolant_is_warning(self):
        state, _ = aio_reader.evaluate_alert(self._snap(coolant_temp_c=52.0))
        self.assertEqual(state, aio_reader.ALERT_WARNING)

    def test_missing_pump_is_not_an_alert(self):
        """AC13: absence of evidence is not a stopped pump."""
        state, reason = aio_reader.evaluate_alert(
            {"pump_rpm": None, "coolant_temp_c": None}
        )
        self.assertEqual(state, aio_reader.ALERT_OK)
        self.assertIsNone(reason)

    def test_critical_coolant_outranks_pump_warning(self):
        state, reason = aio_reader.evaluate_alert(
            self._snap(pump_rpm=300, coolant_temp_c=65.0)
        )
        self.assertEqual(state, aio_reader.ALERT_CRITICAL)
        self.assertIn("Coolant", reason)

    def test_booleans_are_not_readings(self):
        state, _ = aio_reader.evaluate_alert(
            {"pump_rpm": False, "coolant_temp_c": True}
        )
        self.assertEqual(state, aio_reader.ALERT_OK)

    def test_non_dict_is_ok(self):
        self.assertEqual(aio_reader.evaluate_alert(None)[0], aio_reader.ALERT_OK)
