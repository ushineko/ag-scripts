"""Tests for the cooperative cross-process usage cache.

Coordination is verified by mocking ``fetch_claude_usage`` and counting how often
it is actually called, and by exercising the gate / lock / failure paths against a
temporary cache directory.
"""

import os
import time

import pytest

import src.usage_cache as uc

OK = {"five_hour": {"utilization": 42}, "seven_day": {"utilization": 9}}


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point the cache at a temp dir (patch the name `usage_cache` resolves)."""
    monkeypatch.setattr(uc, "get_cache_dir", lambda: tmp_path)
    return tmp_path


def _counter(result):
    calls = {"n": 0}

    def fetch(*_args, **_kwargs):
        calls["n"] += 1
        return result() if callable(result) else result

    return calls, fetch


class TestGate:

    def test_fresh_gate_returns_cache_without_fetching(self, cache_dir, monkeypatch):
        uc._write_cache({"next_attempt_at": time.time() + 999, "fetched_at": time.time(),
                         "data": OK})
        calls, fetch = _counter(OK)
        monkeypatch.setattr(uc, "_default_fetch", fetch)
        data, _ = uc.fetch_usage_cached(60)
        assert data == OK
        assert calls["n"] == 0          # gate not passed -> no API call

    def test_fetches_and_writes_when_empty(self, cache_dir, monkeypatch):
        calls, fetch = _counter(OK)
        monkeypatch.setattr(uc, "_default_fetch", fetch)
        data, fetched_at = uc.fetch_usage_cached(60)
        assert data == OK and calls["n"] == 1
        entry = uc.read_cache()
        assert entry["data"] == OK
        assert entry["next_attempt_at"] > time.time()
        assert entry["fetched_at"] == pytest.approx(fetched_at)

    def test_single_fetch_under_repeat(self, cache_dir, monkeypatch):
        calls, fetch = _counter(OK)
        monkeypatch.setattr(uc, "_default_fetch", fetch)
        results = [uc.fetch_usage_cached(60) for _ in range(5)]
        assert calls["n"] == 1                       # only one real fetch
        assert all(r[0] == OK for r in results)
        assert len({r[1] for r in results}) == 1     # consistent fetched_at

    def test_expired_gate_refetches(self, cache_dir, monkeypatch):
        uc._write_cache({"next_attempt_at": time.time() - 1, "fetched_at": time.time() - 300,
                         "data": OK})
        calls, fetch = _counter(OK)
        monkeypatch.setattr(uc, "_default_fetch", fetch)
        uc.fetch_usage_cached(60)
        assert calls["n"] == 1


class TestLock:

    def test_held_lock_reads_cache_instead_of_fetching(self, cache_dir, monkeypatch):
        pytest.importorskip("fcntl")
        import fcntl

        # Seed good data with an EXPIRED gate (so it would otherwise fetch).
        uc._write_cache({"next_attempt_at": time.time() - 1, "fetched_at": time.time() - 5,
                         "data": OK})
        calls, fetch = _counter(OK)
        monkeypatch.setattr(uc, "_default_fetch", fetch)

        # Simulate another instance holding the lock (separate open fd).
        fd = os.open(str(uc._lock_path()), os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            data, _ = uc.fetch_usage_cached(60)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

        assert data == OK
        assert calls["n"] == 0          # lock held -> did not fetch, used cache


class TestFailure:

    def test_failure_preserves_last_good_and_honors_retry_after(self, cache_dir, monkeypatch):
        uc._write_cache({"next_attempt_at": time.time() - 1, "fetched_at": time.time() - 300,
                         "data": OK})
        monkeypatch.setattr(uc, "_default_fetch",
                            lambda *a, **k: {"error": "rate_limited", "retry_after": 999})
        data, fetched_at = uc.fetch_usage_cached(60)
        assert data == OK                                   # last-good returned
        entry = uc.read_cache()
        assert entry["data"] == OK                          # last-good preserved
        assert entry["next_attempt_at"] - time.time() > 900  # gate pushed by retry_after

    def test_failure_without_prior_returns_error(self, cache_dir, monkeypatch):
        monkeypatch.setattr(uc, "_default_fetch", lambda *a, **k: {"error": "offline"})
        data, fetched_at = uc.fetch_usage_cached(60)
        assert data == {"error": "offline"}
        assert fetched_at is None

    def test_failure_without_retry_after_uses_ttl(self, cache_dir, monkeypatch):
        uc._write_cache({"next_attempt_at": time.time() - 1, "fetched_at": time.time() - 5,
                         "data": OK})
        monkeypatch.setattr(uc, "_default_fetch", lambda *a, **k: {"error": "api_error"})
        uc.fetch_usage_cached(120)
        gate = uc.read_cache()["next_attempt_at"] - time.time()
        assert 100 < gate <= 120                            # ~ttl, not retry_after


class TestIO:

    def test_atomic_round_trip(self, cache_dir):
        entry = {"next_attempt_at": 1.0, "fetched_at": 2.0, "data": OK}
        uc._write_cache(entry)
        assert uc.read_cache() == entry
        assert not list(cache_dir.glob("*.tmp"))            # tmp cleaned up

    def test_corrupt_file_is_treated_as_no_cache(self, cache_dir, monkeypatch):
        uc.get_cache_path().write_text("{ not json")
        assert uc.read_cache() is None
        # ... and a corrupt file doesn't prevent a fetch
        calls, fetch = _counter(OK)
        monkeypatch.setattr(uc, "_default_fetch", fetch)
        uc.fetch_usage_cached(60)
        assert calls["n"] == 1

    def test_missing_file_is_none(self, cache_dir):
        assert uc.read_cache() is None

    def test_no_credentials_persisted(self, cache_dir, monkeypatch):
        monkeypatch.setattr(uc, "_default_fetch", lambda *a, **k: OK)
        uc.fetch_usage_cached(60)
        raw = uc.get_cache_path().read_text()
        assert "accessToken" not in raw and "refreshToken" not in raw
        assert "credential" not in raw.lower()


class TestInjectedFetcher:
    """The fetcher is injected so the mirrored copy can supply its own."""

    def test_explicit_fetch_overrides_the_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(uc, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(uc, "_default_fetch", lambda *a, **k: {"five_hour": {}, "who": "default"})

        data, _ = uc.fetch_usage_cached(60, account="x",
                                        fetch=lambda *a, **k: {"five_hour": {}, "who": "injected"})

        assert data["who"] == "injected"

    def test_missing_fetcher_is_an_explicit_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(uc, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(uc, "_default_fetch", None)

        with pytest.raises(TypeError):
            uc.fetch_usage_cached(60, account="x")

    def test_store_dir_is_passed_through_to_the_fetcher(self, tmp_path, monkeypatch):
        monkeypatch.setattr(uc, "get_cache_dir", lambda: tmp_path)
        seen = []

        uc.fetch_usage_cached(60, account="work", store_dir="/tmp/work",
                              fetch=lambda sd: seen.append(sd) or {"five_hour": {}})

        assert seen == ["/tmp/work"]


class TestForceRefresh:
    """A manual refresh bypasses the freshness gate but still shares its result."""

    def test_force_fetches_inside_the_gate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(uc, "get_cache_dir", lambda: tmp_path)
        calls = []

        def fetch(*_a, **_k):
            calls.append(1)
            return {"five_hour": {"utilization": len(calls)}}

        uc.fetch_usage_cached(600, account="a", fetch=fetch)     # populates, sets gate
        uc.fetch_usage_cached(600, account="a", fetch=fetch)     # inside gate -> cached
        assert len(calls) == 1

        uc.fetch_usage_cached(600, account="a", fetch=fetch, force=True)
        assert len(calls) == 2

    def test_forced_result_is_written_for_other_readers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(uc, "get_cache_dir", lambda: tmp_path)
        uc.fetch_usage_cached(600, account="a",
                              fetch=lambda *a, **k: {"five_hour": {"utilization": 1}})
        uc.fetch_usage_cached(600, account="a", force=True,
                              fetch=lambda *a, **k: {"five_hour": {"utilization": 99}})

        # A different reader, inside the gate, now sees the forced value.
        data, _ = uc.fetch_usage_cached(600, account="a", fetch=lambda *a, **k: 1 / 0)
        assert data["five_hour"]["utilization"] == 99


class TestSharedCacheDir:
    """Both projects must resolve the same directory or they share nothing."""

    def test_linux_path_is_xdg_cache(self, monkeypatch):
        monkeypatch.setattr(uc.sys, "platform", "linux")
        monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/xdg")
        monkeypatch.delenv("LOCALAPPDATA", raising=False)

        assert str(uc.get_cache_dir()) == "/tmp/xdg/claude-usage-widget"

    def test_config_module_delegates_to_the_same_definition(self):
        from src import config

        assert config.get_cache_dir() == uc.get_cache_dir()
