"""Unit tests for herdr-switcher's pure logic (no live herdr / Qt needed).

Covers the parsing and ordering that aren't exercised by the live integration
checks: client-argv → session, MRU ordering, and herdr JSON parsing.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import herdr_api  # noqa: E402
import mru  # noqa: E402
import session_windows as sw  # noqa: E402
from herdr_api import Space  # noqa: E402


def _space(session, wid, number=0, status="idle"):
    return Space(session, wid, f"{session}-{wid}", number, status, False)


class TestSessionFromArgv(unittest.TestCase):
    def test_bare_herdr_is_default(self):
        self.assertEqual(sw._session_from_argv(["herdr"]), "default")

    def test_server_is_not_a_client(self):
        self.assertIsNone(sw._session_from_argv(["herdr", "server"]))

    def test_session_attach_named(self):
        self.assertEqual(
            sw._session_from_argv(["herdr", "session", "attach", "work"]), "work"
        )

    def test_session_flag(self):
        self.assertEqual(
            sw._session_from_argv(["herdr", "--session", "work", "workspace", "list"]),
            "work",
        )

    def test_absolute_path_basename(self):
        self.assertEqual(sw._session_from_argv(["/usr/bin/herdr"]), "default")

    def test_non_herdr_is_none(self):
        self.assertIsNone(sw._session_from_argv(["bash", "-c", "herdr"]))


class TestMru(unittest.TestCase):
    def test_touch_moves_to_front_and_dedupes(self):
        keys = ["a", "b", "c"]
        keys = mru.touch(keys, "c")
        self.assertEqual(keys, ["c", "a", "b"])
        keys = mru.touch(keys, "d")
        self.assertEqual(keys, ["d", "c", "a", "b"])

    def test_order_spaces_recent_first_then_unseen_sorted(self):
        spaces = [
            _space("default", "w1", 2),
            _space("default", "w3", 3),
            _space("work", "w1", 1),
            _space("work", "w2", 3),
        ]
        keys = ["default/w3", "work/w1"]  # most-recent first
        ordered = mru.order_spaces(spaces, keys)
        self.assertEqual([s.key for s in ordered[:2]], ["default/w3", "work/w1"])
        # unseen appended, sorted by (session, number)
        self.assertEqual([s.key for s in ordered[2:]], ["default/w1", "work/w2"])

    def test_order_spaces_ignores_stale_keys(self):
        spaces = [_space("default", "w1")]
        ordered = mru.order_spaces(spaces, ["work/w9", "default/w1"])
        self.assertEqual([s.key for s in ordered], ["default/w1"])


class TestHerdrApiParsing(unittest.TestCase):
    def setUp(self):
        self._orig = herdr_api._run

    def tearDown(self):
        herdr_api._run = self._orig

    def test_list_sessions(self):
        herdr_api._run = lambda args, **k: (
            '{"sessions":[{"name":"default","default":true,"running":true,'
            '"socket_path":"/s"},{"name":"work","default":false,"running":true,'
            '"socket_path":"/w"}]}'
        )
        sessions = herdr_api.list_sessions()
        self.assertEqual([s.name for s in sessions], ["default", "work"])
        self.assertTrue(sessions[0].default)

    def test_list_spaces(self):
        herdr_api._run = lambda args, **k: (
            '{"result":{"type":"workspace_list","workspaces":['
            '{"workspace_id":"w1","label":"sysadmin","number":2,'
            '"agent_status":"working","focused":true}]}}'
        )
        spaces = herdr_api.list_spaces("default")
        self.assertEqual(len(spaces), 1)
        self.assertEqual(spaces[0].label, "sysadmin")
        self.assertEqual(spaces[0].key, "default/w1")
        self.assertTrue(spaces[0].focused)

    def test_bad_json_raises(self):
        herdr_api._run = lambda args, **k: "not json"
        with self.assertRaises(herdr_api.HerdrError):
            herdr_api.list_sessions()


if __name__ == "__main__":
    unittest.main()
