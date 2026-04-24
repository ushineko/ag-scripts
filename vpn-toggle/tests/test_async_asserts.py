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

    def test_success_when_prefix_matches(self, qapp, monkeypatch):
        """Inject a fake QDnsLookup whose finished signal fires with one A record."""
        from PyQt6.QtCore import QObject, pyqtSignal

        class FakeRecord:
            def value(self):
                return _FakeAddr()

        class _FakeAddr:
            def toString(self):
                return "10.1.2.3"

        class FakeLookup(QObject):
            finished = pyqtSignal()

            def __init__(self, parent=None):
                super().__init__(parent)
                self._err = 0

            def setType(self, *_):
                pass

            def setName(self, *_):
                pass

            def lookup(self):
                QTimer.singleShot(0, self.finished.emit)

            def error(self):
                # Match QDnsLookup.Error.NoError enum value
                from PyQt6.QtNetwork import QDnsLookup
                return QDnsLookup.Error.NoError

            def hostAddressRecords(self):
                return [FakeRecord()]

            def abort(self):
                pass

            def errorString(self):
                return ""

        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'example.com', 'expected_prefix': '10.'})
        assert_obj._make_lookup = lambda hostname: FakeLookup(assert_obj)

        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert len(results) == 1
        assert results[0].success is True
        assert '10.1.2.3' in results[0].message
        assert results[0].details['ip'] == '10.1.2.3'

    def test_failure_when_prefix_mismatch(self, qapp):
        from PyQt6.QtCore import QObject, pyqtSignal
        from PyQt6.QtNetwork import QDnsLookup

        class _Rec:
            def value(self):
                class A:
                    def toString(self_):
                        return "192.168.1.1"
                return A()

        class FakeLookup(QObject):
            finished = pyqtSignal()

            def setType(self, *_): pass
            def setName(self, *_): pass
            def lookup(self): QTimer.singleShot(0, self.finished.emit)
            def error(self): return QDnsLookup.Error.NoError
            def hostAddressRecords(self): return [_Rec()]
            def abort(self): pass
            def errorString(self): return ""

        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'example.com', 'expected_prefix': '10.'})
        assert_obj._make_lookup = lambda hostname: FakeLookup(assert_obj)

        results = collect_completion(assert_obj)
        assert_obj.start()
        pump_events(predicate=lambda: len(results) > 0)
        assert results[0].success is False
        assert 'expected prefix' in results[0].message.lower()

    def test_lookup_error_reports_failure(self, qapp):
        from PyQt6.QtCore import QObject, pyqtSignal
        from PyQt6.QtNetwork import QDnsLookup

        class FakeLookup(QObject):
            finished = pyqtSignal()

            def setType(self, *_): pass
            def setName(self, *_): pass
            def lookup(self): QTimer.singleShot(0, self.finished.emit)
            def error(self): return QDnsLookup.Error.ResolverError
            def hostAddressRecords(self): return []
            def abort(self): pass
            def errorString(self): return "nope"

        assert_obj = AsyncDNSLookupAssert(
            {'hostname': 'missing.example', 'expected_prefix': '1.'})
        assert_obj._make_lookup = lambda hostname: FakeLookup(assert_obj)

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
