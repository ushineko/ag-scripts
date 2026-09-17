"""Spec 021: LCD dashboard rendering and the change-gate that limits pushes."""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import aio_dashboard  # noqa: E402

_app = QApplication.instance() or QApplication([])

HEALTHY = {"coolant_temp_c": 36.8, "cpu_temp_c": 54.0, "pump_rpm": 1727,
           "alert_state": "ok"}
CRITICAL = {"coolant_temp_c": 63.2, "cpu_temp_c": 99.0, "pump_rpm": 0,
            "alert_state": "critical", "alert_reason": "Pump stopped (0 rpm)"}
EMPTY = {"coolant_temp_c": None, "cpu_temp_c": None, "pump_rpm": None,
         "alert_state": "ok"}


class TestRender(unittest.TestCase):
    """021 AC7/AC8."""

    def test_native_lcd_resolution(self):
        image = aio_dashboard.render_dashboard(HEALTHY)
        self.assertEqual((image.width(), image.height()), (640, 640))
        self.assertEqual((image.width(), image.height()), aio_dashboard.SIZE and
                         (aio_dashboard.SIZE, aio_dashboard.SIZE))

    def test_renders_every_state_without_raising(self):
        for snap in (HEALTHY, CRITICAL, EMPTY, {}, None):
            with self.subTest(snap=snap):
                image = aio_dashboard.render_dashboard(snap)
                self.assertFalse(image.isNull())

    def test_missing_values_degrade_to_placeholders(self):
        self.assertEqual(aio_dashboard.content_key(EMPTY)[:3], ("--", "--", "--"))

    def test_writes_png(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "lcd.png")
            self.assertTrue(aio_dashboard.write_png(
                aio_dashboard.render_dashboard(HEALTHY), path))
            self.assertGreater(os.path.getsize(path), 0)

    def test_write_failure_returns_false(self):
        self.assertFalse(aio_dashboard.write_png(
            aio_dashboard.render_dashboard(HEALTHY), "/proc/nope/lcd.png"))


class TestChangeGate(unittest.TestCase):
    """021 AC9 — the main defence against liquidctl#774 is not writing."""

    def test_subdegree_drift_does_not_change_the_key(self):
        a = dict(HEALTHY)
        b = dict(HEALTHY, coolant_temp_c=36.84, cpu_temp_c=54.4)
        self.assertEqual(aio_dashboard.content_key(a), aio_dashboard.content_key(b))

    def test_a_whole_degree_does_change_the_key(self):
        b = dict(HEALTHY, coolant_temp_c=38.0)
        self.assertNotEqual(aio_dashboard.content_key(HEALTHY),
                            aio_dashboard.content_key(b))

    def test_pump_rpm_change_is_visible(self):
        b = dict(HEALTHY, pump_rpm=0)
        self.assertNotEqual(aio_dashboard.content_key(HEALTHY),
                            aio_dashboard.content_key(b))

    def test_alert_state_change_is_visible(self):
        b = dict(HEALTHY, alert_state="critical")
        self.assertNotEqual(aio_dashboard.content_key(HEALTHY),
                            aio_dashboard.content_key(b))

    def test_non_dict_is_safe(self):
        self.assertEqual(len(aio_dashboard.content_key(None)), 4)


if __name__ == "__main__":
    unittest.main()


class TestPushGate(unittest.TestCase):
    """The gate that decides how often the LCD is written at all.

    Keying on CPU temperature at whole degrees was a design error: an idle
    i9-14900K wanders continuously, so the gate never suppressed anything and
    the screen was rewritten every interval.
    """

    BASE = {"coolant_temp_c": 36.8, "cpu_temp_c": 50.0, "pump_rpm": 1727,
            "alert_state": "ok"}

    def _v(self, **kw):
        return dict(self.BASE, **kw)

    def test_first_push_always_happens(self):
        self.assertTrue(aio_dashboard.should_push(self.BASE, None))

    def test_identical_snapshot_does_not_push(self):
        self.assertFalse(aio_dashboard.should_push(self.BASE, self.BASE))

    # -- the bug this fixes ------------------------------------------------

    def test_small_cpu_wander_does_not_push(self):
        """The actual regression: CPU drifting a few degrees forced a write."""
        for cpu in (51.0, 52.5, 46.0, 54.9):
            with self.subTest(cpu=cpu):
                self.assertFalse(
                    aio_dashboard.should_push(self._v(cpu_temp_c=cpu), self.BASE))

    def test_large_cpu_change_does_push(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(cpu_temp_c=90.0), self.BASE))

    def test_cpu_threshold_is_compared_against_what_is_on_screen(self):
        """A value creeping up in small steps must still eventually redraw.

        Comparing each sample against the previous *sample* would let CPU walk
        arbitrarily far from the displayed figure without ever tripping.
        """
        last = self.BASE
        for cpu in (52.0, 54.0, 56.0):
            pushed = aio_dashboard.should_push(self._v(cpu_temp_c=cpu), last)
        self.assertTrue(pushed, "56 C is >= 5 C from the displayed 50 C")

    # -- things that must never be suppressed ------------------------------

    def test_coolant_change_always_pushes(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(coolant_temp_c=37.8), self.BASE))

    def test_subdegree_coolant_drift_does_not_push(self):
        self.assertFalse(
            aio_dashboard.should_push(self._v(coolant_temp_c=36.84), self.BASE))

    def test_alert_state_change_always_pushes(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(alert_state="critical"), self.BASE))

    def test_pump_stopping_always_pushes(self):
        """The one transition that must never be thresholded away."""
        self.assertTrue(
            aio_dashboard.should_push(self._v(pump_rpm=0), self.BASE))

    def test_pump_starting_always_pushes(self):
        stopped = self._v(pump_rpm=0)
        self.assertTrue(aio_dashboard.should_push(self.BASE, stopped))

    def test_small_pump_jitter_does_not_push(self):
        self.assertFalse(
            aio_dashboard.should_push(self._v(pump_rpm=1740), self.BASE))

    def test_large_pump_change_does_push(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(pump_rpm=1200), self.BASE))

    # -- appearing / disappearing values -----------------------------------

    def test_value_becoming_unavailable_pushes(self):
        for field in ("cpu_temp_c", "pump_rpm", "coolant_temp_c"):
            with self.subTest(field=field):
                self.assertTrue(
                    aio_dashboard.should_push(self._v(**{field: None}), self.BASE))

    def test_value_becoming_available_pushes(self):
        missing = self._v(cpu_temp_c=None)
        self.assertTrue(aio_dashboard.should_push(self.BASE, missing))

    def test_garbage_new_snapshot_does_not_push(self):
        for bad in (None, "x", 5):
            with self.subTest(bad=bad):
                self.assertFalse(aio_dashboard.should_push(bad, self.BASE))

    def test_booleans_are_not_readings(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(cpu_temp_c=True), self.BASE))


class TestBackground(unittest.TestCase):
    """Spec 024: the starfield is generated once and never changes."""

    def test_background_is_cached(self):
        first = aio_dashboard._background()
        self.assertIs(aio_dashboard._background(), first)

    def test_background_is_lcd_sized(self):
        bg = aio_dashboard._background()
        self.assertEqual((bg.width(), bg.height()),
                         (aio_dashboard.SIZE, aio_dashboard.SIZE))

    def test_renders_are_pixel_identical_for_identical_input(self):
        """A per-frame starfield would shimmer between updates.

        On a screen that only redraws when something changes, shimmer reads as
        a fault rather than decoration — so the sky must be deterministic.
        """
        a = aio_dashboard.render_dashboard(HEALTHY)
        b = aio_dashboard.render_dashboard(HEALTHY)
        self.assertEqual(a.bits().asstring(a.sizeInBytes()),
                         b.bits().asstring(b.sizeInBytes()))

    def test_background_survives_a_cache_reset(self):
        # A dict keyed by tint since spec 030, not a single cached image.
        aio_dashboard._background_cache = {}
        self.assertFalse(aio_dashboard._background().isNull())

    def test_render_does_not_mutate_the_cached_background(self):
        """render_dashboard copies; drawing into the cache would accumulate."""
        bg = aio_dashboard._background()
        before = bg.bits().asstring(bg.sizeInBytes())
        aio_dashboard.render_dashboard(CRITICAL)
        after = aio_dashboard._background().bits().asstring(bg.sizeInBytes())
        self.assertEqual(before, after)


class TestSeverityColours(unittest.TestCase):
    """A stopped pump must not be drawn in the calm accent colour."""

    def test_stopped_pump_renders_without_error(self):
        image = aio_dashboard.render_dashboard(CRITICAL)
        self.assertFalse(image.isNull())

    def test_cpu_is_never_graded(self):
        """Deliberate: a 14900K at 100 C is normal and must not read as alarm."""
        hot = dict(HEALTHY, cpu_temp_c=100.0)
        self.assertFalse(aio_dashboard.render_dashboard(hot).isNull())


class TestGifOutput(unittest.TestCase):
    """028: the firmware retains a GIF but drops a static image.

    Measured on the hardware: a pushed PNG reverted to the built-in display in
    ~5-10 s with nothing else touching the cooler, while a GIF kept playing.
    That is why the dashboard looked like it was "bouncing" between the two.
    """

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def _path(self, name="lcd.gif"):
        return os.path.join(self.dir.name, name)

    def test_writes_a_real_gif(self):
        path = self._path()
        self.assertTrue(aio_dashboard.write_gif(
            aio_dashboard.render_dashboard(HEALTHY), path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(3), b"GIF", "must be a GIF, not a PNG")

    def test_gif_is_native_lcd_resolution(self):
        from PIL import Image
        path = self._path()
        aio_dashboard.write_gif(aio_dashboard.render_dashboard(HEALTHY), path)
        with Image.open(path) as im:
            self.assertEqual(im.size, (aio_dashboard.SIZE, aio_dashboard.SIZE))

    def test_single_frame_is_enough(self):
        """One frame exploits the retention; animation is not the point."""
        from PIL import Image
        path = self._path()
        aio_dashboard.write_gif(aio_dashboard.render_dashboard(HEALTHY), path)
        with Image.open(path) as im:
            self.assertEqual(getattr(im, "n_frames", 1), 1)

    def test_creates_missing_directories(self):
        path = os.path.join(self.dir.name, "sub", "dir", "lcd.gif")
        self.assertTrue(aio_dashboard.write_gif(
            aio_dashboard.render_dashboard(HEALTHY), path))
        self.assertTrue(os.path.exists(path))

    def test_write_failure_returns_false(self):
        self.assertFalse(aio_dashboard.write_gif(
            aio_dashboard.render_dashboard(HEALTHY), "/proc/nope/lcd.gif"))

    def test_renders_every_state_to_gif(self):
        for snap in (HEALTHY, CRITICAL, EMPTY):
            with self.subTest(snap=snap):
                path = self._path(f"{id(snap)}.gif")
                self.assertTrue(aio_dashboard.write_gif(
                    aio_dashboard.render_dashboard(snap), path))
                self.assertGreater(os.path.getsize(path), 0)


class TestComplementaryTint(unittest.TestCase):
    """030: the dashboard is tinted complementary to the lighting colour."""

    def tearDown(self):
        aio_dashboard._background_cache = {}

    def test_complement_rotates_hue_180(self):
        cases = {
            (255, 0, 0): (0, 255, 255),     # red   -> cyan
            (0, 255, 0): (255, 0, 255),     # green -> magenta
            (0, 0, 255): (255, 255, 0),     # blue  -> yellow
        }
        for primary, expected in cases.items():
            with self.subTest(primary=primary):
                self.assertEqual(aio_dashboard.complement(primary), expected)

    def test_complement_rotates_hue_by_180(self):
        """The real contract. Exact round-trip equality is NOT the contract.

        RGB -> HSV -> RGB is lossy, so complement(complement(x)) drifts a few
        units: (12,200,90) round-trips to (12,200,84). Asserting equality tested
        a property nothing depends on; hue opposition is what the feature means.
        """
        # colorsys, not QColor: importing PyQt6 inside a test resolves at call
        # time, and another test module stubs PyQt6 in sys.modules at collection,
        # so QColor here would be a MagicMock. Pure stdlib is immune to that.
        import colorsys

        def hue_deg(rgb):
            r, g, b = (c / 255.0 for c in rgb)
            return colorsys.rgb_to_hsv(r, g, b)[0] * 360.0

        for rgb in ((255, 0, 0), (12, 200, 90), (128, 0, 255), (200, 120, 30)):
            with self.subTest(rgb=rgb):
                delta = abs(hue_deg(rgb) - hue_deg(aio_dashboard.complement(rgb))) % 360
                self.assertAlmostEqual(min(delta, 360 - delta), 180, delta=3)

    def test_greys_have_no_complement(self):
        """A hueless colour rotates to itself rather than to something arbitrary."""
        for grey in ((0, 0, 0), (128, 128, 128), (255, 255, 255)):
            with self.subTest(grey=grey):
                self.assertEqual(aio_dashboard.complement(grey), grey)

    def test_tint_changes_the_rendered_image(self):
        plain = aio_dashboard.render_dashboard(HEALTHY)
        tinted = aio_dashboard.render_dashboard(HEALTHY, (255, 0, 0))
        self.assertNotEqual(plain.bits().asstring(plain.sizeInBytes()),
                            tinted.bits().asstring(tinted.sizeInBytes()))

    def test_different_tints_differ(self):
        red = aio_dashboard.render_dashboard(HEALTHY, (255, 0, 0))
        blue = aio_dashboard.render_dashboard(HEALTHY, (0, 0, 255))
        self.assertNotEqual(red.bits().asstring(red.sizeInBytes()),
                            blue.bits().asstring(blue.sizeInBytes()))

    def test_none_tint_matches_the_untinted_render(self):
        a = aio_dashboard.render_dashboard(HEALTHY, None)
        b = aio_dashboard.render_dashboard(HEALTHY)
        self.assertEqual(a.bits().asstring(a.sizeInBytes()),
                         b.bits().asstring(b.sizeInBytes()))

    def test_coolant_severity_is_never_retinted(self):
        """The coolant colour IS the reading; a scene must not restyle it.

        A hot coolant drawn in a scene's calm colour would defeat the screen's
        only real purpose, so the severity palette is checked directly.
        """
        self.assertEqual(aio_dashboard._coolant_color(65.0), aio_dashboard._CRIT)
        self.assertEqual(aio_dashboard._coolant_color(52.0), aio_dashboard._WARN)
        self.assertEqual(aio_dashboard._coolant_color(36.0), aio_dashboard._OK)

    def test_tint_palette_defaults_without_a_tint(self):
        accent, nebulae = aio_dashboard._tint_palette(None)
        self.assertEqual(accent, aio_dashboard._ACCENT)
        self.assertEqual(nebulae, aio_dashboard._NEBULAE)

    def test_tint_palette_keeps_nebula_geometry(self):
        """Only the colours change; positions and radii are the composition."""
        _, tinted = aio_dashboard._tint_palette((255, 0, 0))
        for (fx, fy, fr, _), (ox, oy, orad, _o) in zip(tinted, aio_dashboard._NEBULAE):
            self.assertEqual((fx, fy, fr), (ox, oy, orad))

    def test_background_cache_is_per_tint(self):
        aio_dashboard._background_cache = {}
        aio_dashboard._background(None)
        aio_dashboard._background((255, 0, 0))
        self.assertEqual(len(aio_dashboard._background_cache), 2)

    def test_background_cache_is_bounded(self):
        aio_dashboard._background_cache = {}
        for i in range(30):
            aio_dashboard._background((i * 8 % 256, 40, 200))
        self.assertLessEqual(len(aio_dashboard._background_cache), 25)

    def test_render_never_raises_on_a_bad_tint(self):
        for bad in ("red", 17, (1, 2), (1, 2, 3, 4)):
            with self.subTest(bad=bad):
                img = aio_dashboard.render_dashboard(HEALTHY, bad)
                self.assertFalse(img.isNull())
