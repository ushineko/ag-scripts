"""
Tests for the event-driven async assert variants (spec 009).

These exercise the QObject-based AsyncDNSLookupAssert / AsyncGeolocationAssert /
AsyncPingAssert classes by replacing their primitive-creation hooks with fakes
that drive the `completed(AssertResult)` signal synchronously.
"""
import time
from typing import List
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication, QTimer

from vpn_toggle.asserts import (
    AssertResult,
    AsyncDNSLookupAssert,
    AsyncGeolocationAssert,
    AsyncPingAssert,
    create_async_assert,
)


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def collect_completion(obj) -> List[AssertResult]:
    """Connect to `completed` and return a list that the signal appends into."""
    results: List[AssertResult] = []
    obj.completed.connect(results.append)
    return results


def pump_events(timeout_ms: int = 1000, predicate=None):
    """Pump the Qt event loop until predicate() is truthy or timeout."""
    start = time.monotonic()
    while (time.monotonic() - start) * 1000 < timeout_ms:
        QCoreApplication.processEvents()
        if predicate is None or predicate():
            return True
        time.sleep(0.005)
    return False


class _FakeGetentProcess:
    """Stand-in for QProcess wired to AsyncDNSLookupAssert via `_make_process`.

    Exposes only the surface that AsyncDNSLookupAssert touches: a `finished`
    signal carrying (exit_code, exit_status), `start()` that schedules the
    signal, `readAllStandardOutput()`, `errorOccurred`, `state()`, `kill()`.
    """
    def __init__(self, parent, exit_code: int, stdout: bytes):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Inner(QObject):
            finished = pyqtSignal(int, object)
            errorOccurred = pyqtSignal(object)

        self._inner = _Inner(parent)
        self.finished = self._inner.finished
        self.errorOccurred = self._inner.errorOccurred
        self._exit_code = exit_code
        self._stdout = stdout
        self._killed = False

    def start(self, _program, _args):
        QTimer.singleShot(0, lambda: self.finished.emit(self._exit_code, None))

    def readAllStandardOutput(self):
        return self._stdout

    def state(self):
        from PyQt6.QtCore import QProcess
        return QProcess.ProcessState.NotRunning

    def kill(self):
        self._killed = True

    def errorString(self):
        return ""


class TestFactory:

    def test_dispatch_dns_lookup(self, qapp):
        obj = create_async_assert({'type': 'dns_lookup',
                                   'hostname': 'x', 'expected_prefix': '1.'})
        assert isinstance(obj, AsyncDNSLookupAssert)

    def test_dispatch_geolocation(self, qapp):
        obj = create_async_assert({'type': 'geolocation',
                                   'expected_value': 'vegas'})
        assert isinstance(obj, AsyncGeolocationAssert)

    def test_dispatch_ping(self, qapp):
        obj = create_async_assert({'type': 'ping', 'host': '127.0.0.1'})
        assert isinstance(obj, AsyncPingAssert)

    def test_unknown_type_raises(self, qapp):
        with pytest.raises(ValueError):
            create_async_assert({'type': 'nope'})


class TestAsyncDNSLookup:

    def test_missing_hostname_reports_failure(self, qapp):
        assert_obj = AsyncDNSLookupAssert({'expected_prefix': '1.'})
        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert len(results) == 1
        assert results[0].success is False
        assert 'missing' in results[0].message.lower()

    def test_missing_expected_prefix_reports_failure(self, qapp):
        assert_obj = AsyncDNSLookupAssert({'hostname': 'example.com'})
        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert len(results) == 1
        assert results[0].success is False

    def test_success_when_prefix_matches(self, qapp):
        """Inject a fake QProcess whose finished signal fires with getent stdout."""
        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'example.com', 'expected_prefix': '10.'})
        fake = _FakeGetentProcess(
            assert_obj, exit_code=0, stdout=b"10.1.2.3  example.com\n")
        assert_obj._make_process = lambda: fake

        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert len(results) == 1
        assert results[0].success is True
        assert '10.1.2.3' in results[0].message
        assert results[0].details['ip'] == '10.1.2.3'

    def test_first_ipv4_record_used_when_multiple_returned(self, qapp):
        """`getent hosts` returns one line per record; the first IPv4 is the verdict."""
        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'multi.example', 'expected_prefix': '100.'})
        fake = _FakeGetentProcess(
            assert_obj, exit_code=0,
            stdout=(b"100.64.1.5  multi.example\n"
                    b"100.64.1.6  multi.example\n"))
        assert_obj._make_process = lambda: fake

        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is True
        assert results[0].details['ip'] == '100.64.1.5'

    def test_ipv6_only_response_reports_no_ipv4(self, qapp):
        """AAAA-only hosts should fail since the prefix check is IPv4-shaped."""
        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'v6.example', 'expected_prefix': '10.'})
        fake = _FakeGetentProcess(
            assert_obj, exit_code=0,
            stdout=b"2607:f8b0:4007:806::200e  v6.example\n")
        assert_obj._make_process = lambda: fake

        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is False
        assert 'no ipv4' in results[0].message.lower()

    def test_failure_when_prefix_mismatch(self, qapp):
        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'example.com', 'expected_prefix': '10.'})
        fake = _FakeGetentProcess(
            assert_obj, exit_code=0, stdout=b"192.168.1.1  example.com\n")
        assert_obj._make_process = lambda: fake

        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is False
        assert 'expected prefix' in results[0].message.lower()

    def test_lookup_error_reports_failure(self, qapp):
        """Non-zero exit from `getent` (host not found) surfaces as resolution failure."""
        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'missing.example', 'expected_prefix': '1.'})
        fake = _FakeGetentProcess(assert_obj, exit_code=2, stdout=b"")
        assert_obj._make_process = lambda: fake

        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is False
        assert 'could not resolve' in results[0].message.lower()


class TestAsyncGeolocation:

    def test_missing_expected_value_reports_failure(self, qapp):
        obj = AsyncGeolocationAssert({'field': 'city'})
        results = collect_completion(obj)
        obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is False

    def test_success_path(self, qapp):
        """Fake QNetworkReply that emits finished with JSON body."""
        from PyQt6.QtCore import QObject, pyqtSignal
        from PyQt6.QtNetwork import QNetworkReply

        class FakeReply(QObject):
            finished = pyqtSignal()

            def __init__(self, body: bytes, parent=None):
                super().__init__(parent)
                self._body = body

            def error(self):
                return QNetworkReply.NetworkError.NoError

            def readAll(self):
                return self._body

            def errorString(self):
                return ""

            def abort(self):
                pass

            def deleteLater(self):
                pass

        body = (
            b'{"status":"success","city":"Las Vegas","regionName":"Nevada",'
            b'"country":"USA","query":"1.2.3.4"}'
        )
        obj = AsyncGeolocationAssert({'field': 'city', 'expected_value': 'Vegas'})

        def make_req():
            reply = FakeReply(body, parent=obj)
            QTimer.singleShot(0, reply.finished.emit)
            return reply

        obj._make_request = make_req
        results = collect_completion(obj)
        obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is True
        assert results[0].details['actual'] == 'Las Vegas'


class TestAsyncPing:

    def test_missing_host_reports_failure(self, qapp):
        obj = AsyncPingAssert({})
        results = collect_completion(obj)
        obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is False

    def test_loopback_reachable(self, qapp):
        """Smoke test against real loopback — 127.0.0.1 should always ping."""
        obj = AsyncPingAssert({'host': '127.0.0.1', 'timeout_seconds': 2})
        results = collect_completion(obj)
        obj.start()
        pump_events(timeout_ms=5000, predicate=lambda: len(results) > 0)
        assert len(results) == 1
        assert results[0].success is True
        assert '127.0.0.1' in results[0].message
