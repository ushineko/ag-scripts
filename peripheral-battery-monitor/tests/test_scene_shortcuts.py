"""Spec 029: KWin caches scripts by path, so each install needs a fresh one.

The shortcuts broke across a reboot and could not be recovered by restarting the
monitor. `install()` reported success, `isScriptLoaded` reported true, the file
on disk was correct — and KWin was running a stale script, because `loadScript`
on a previously-seen path returns the cached id without re-reading the file.
"""

import os
import sys
import time
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import scene_shortcuts  # noqa: E402


class TestUniqueScriptPath(unittest.TestCase):
    """029 AC1 - the cache cannot be defeated by a stable path."""

    def test_each_call_returns_a_new_path(self):
        paths = {scene_shortcuts._script_path() for _ in range(5)}
        self.assertEqual(len(paths), 5, "a reused path gets a cached, stale script")

    def test_paths_are_distinct_across_time(self):
        first = scene_shortcuts._script_path()
        time.sleep(0.001)
        self.assertNotEqual(first, scene_shortcuts._script_path())

    def test_path_is_in_the_runtime_dir(self):
        self.assertTrue(
            scene_shortcuts._script_path().startswith(scene_shortcuts._script_dir()))

    def test_path_carries_the_script_name(self):
        self.assertIn(scene_shortcuts.SCRIPT_NAME,
                      os.path.basename(scene_shortcuts._script_path()))

    def test_path_is_a_js_file(self):
        self.assertTrue(scene_shortcuts._script_path().endswith(".js"))


class TestStaleCleanup(unittest.TestCase):
    """029 AC2 - unique paths must not accumulate files."""

    def setUp(self):
        self.made = []

    def tearDown(self):
        for p in self.made:
            try:
                os.unlink(p)
            except OSError:
                pass

    def test_finds_generated_siblings(self):
        p = scene_shortcuts._script_path()
        with open(p, "w") as f:
            f.write("// test\n")
        self.made.append(p)
        self.assertIn(p, scene_shortcuts._stale_script_files())

    def test_ignores_unrelated_files(self):
        directory = scene_shortcuts._script_dir()
        p = os.path.join(directory, "something-else.js")
        with open(p, "w") as f:
            f.write("// not ours\n")
        self.made.append(p)
        self.assertNotIn(p, scene_shortcuts._stale_script_files())

    def test_missing_directory_is_not_an_error(self):
        original = scene_shortcuts._script_dir
        scene_shortcuts._script_dir = lambda: "/nonexistent/dir/xyz"
        try:
            self.assertEqual(scene_shortcuts._stale_script_files(), [])
        finally:
            scene_shortcuts._script_dir = original


class TestGeneratedScript(unittest.TestCase):
    """029 AC5 - the KWin half must be visible in the journal."""

    def test_logs_registration_count(self):
        js = scene_shortcuts.build_js([1, 2, 3])
        self.assertIn("registering", js)
        self.assertIn("3", js)

    def test_logs_each_activation(self):
        js = scene_shortcuts.build_js([1])
        self.assertIn("shortcut fired", js)

    def test_registers_one_shortcut_per_slot(self):
        js = scene_shortcuts.build_js([1, 2, 3])
        self.assertEqual(js.count("registerShortcut"), 3)

    def test_each_callback_is_its_own_closure(self):
        """A bare loop variable would point every shortcut at the last slot."""
        js = scene_shortcuts.build_js([1, 2])
        self.assertEqual(js.count("(function(slot, key)"), 2)

    def test_calls_the_monitor_over_dbus(self):
        """Asserted as literals, not via scene_service.

        Another test in the suite replaces `scene_service` in sys.modules with a
        MagicMock, and it leaks: reading the constants from the module here made
        this test pass alone and fail in the suite. The literals are also the
        stronger assertion — they are the contract the KWin script and the D-Bus
        endpoint must agree on.
        """
        js = scene_shortcuts.build_js([1])
        self.assertIn("org.agscripts.PeripheralBatteryMonitor", js)
        self.assertIn("org.agscripts.Scenes", js)
        self.assertIn("/Scenes", js)


if __name__ == "__main__":
    unittest.main()
