from __future__ import annotations

from dataclasses import replace

import pytest

from slack_presence_toggle.config import Config
from slack_presence_toggle.slack_client import ApiHealth, ProfileStatus
from slack_presence_toggle.state_machine import (
    FocusState,
    FocusStateMachine,
)


class FakeSlack:
    def __init__(self):
        self.set_presence_calls: list[str] = []
        self.set_profile_status_calls: list[tuple[str, str, int]] = []
        self.get_profile_status_calls = 0
        self.profile_status = ProfileStatus(text="", emoji="", expiration=0)

        # Default: every call succeeds. Override per-test.
        self.set_presence_response: ApiHealth = ApiHealth.success()
        self.set_profile_response: ApiHealth = ApiHealth.success()
        self.get_profile_response: ApiHealth = ApiHealth.success()

    def set_presence(self, presence):
        self.set_presence_calls.append(presence)
        return self.set_presence_response

    def set_profile_status(self, text, emoji, expiration):
        self.set_profile_status_calls.append((text, emoji, expiration))
        if self.set_profile_response.ok:
            self.profile_status = ProfileStatus(text=text, emoji=emoji, expiration=expiration)
        return self.set_profile_response

    def get_profile_status(self):
        self.get_profile_status_calls += 1
        return self.get_profile_response, self.profile_status


class FakeScheduler:
    def __init__(self):
        self.scheduled: list[tuple[float, callable, int]] = []  # (delay, cb, id)
        self._next_id = 0

    def schedule(self, delay, callback):
        self._next_id += 1
        h = (delay, callback, self._next_id)
        self.scheduled.append(h)
        return h

    def cancel(self, handle):
        if handle in self.scheduled:
            self.scheduled.remove(handle)

    def fire_next(self):
        """Fire the earliest-scheduled callback."""
        delay, cb, _ = self.scheduled.pop(0)
        cb()


class FakeClock:
    def __init__(self, now: float = 1_700_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def setup():
    """Returns a factory: setup(**config_overrides) -> (fsm, slack, scheduler, clock)."""
    def _make(**overrides):
        cfg = Config(**overrides)
        slack = FakeSlack()
        scheduler = FakeScheduler()
        clock = FakeClock()
        fsm = FocusStateMachine(slack=slack, scheduler=scheduler, config=cfg, clock=clock)
        return fsm, slack, scheduler, clock
    return _make


@pytest.fixture
def setup_with_observer():
    """Like `setup` but installs an observer that records internal transitions."""
    def _make(**overrides):
        cfg = Config(**overrides)
        slack = FakeSlack()
        scheduler = FakeScheduler()
        clock = FakeClock()
        observed: list[tuple] = []
        def observer(result, prev_snapshot, label):
            observed.append((result, prev_snapshot, label))
        fsm = FocusStateMachine(
            slack=slack, scheduler=scheduler, config=cfg, clock=clock,
            on_internal_transition=observer,
        )
        return fsm, slack, scheduler, clock, observed
    return _make


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_state_is_slack_focused_not_forced(setup):
    """Initial state assumes Slack is focused so that a startup
    non-Slack-window event correctly transitions to pending-away."""
    fsm, slack, scheduler, _ = setup()
    snap = fsm.snapshot
    assert snap.enabled is True
    assert snap.focus == FocusState.SLACK_FOCUSED
    assert snap.we_forced_away is False
    assert snap.we_forced_status is False
    assert scheduler.scheduled == []


def test_disabled_in_config_starts_disabled(setup):
    fsm, *_ = setup(enabled=False)
    assert fsm.snapshot.enabled is False


def test_first_event_is_non_slack_schedules_grace_timer(setup):
    """User's reported scenario: app starts with Slack unfocused. The
    KWin script's initial-active-window emit should land as a non-Slack
    event and trigger the grace timer."""
    fsm, _, scheduler, _ = setup(grace_seconds=30)
    fsm.on_window_activated("firefox")  # very first event after startup
    assert len(scheduler.scheduled) == 1
    assert scheduler.scheduled[0][0] == 30
    assert fsm.snapshot.focus == FocusState.OTHER_FOCUSED_PENDING_AWAY


def test_first_event_is_slack_does_not_schedule(setup):
    """Mirror of the above: if Slack happens to be focused at startup,
    the very first event is a Slack window, no timer."""
    fsm, _, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    assert scheduler.scheduled == []
    assert fsm.snapshot.focus == FocusState.SLACK_FOCUSED


# ---------------------------------------------------------------------------
# Slack focus from clean state
# ---------------------------------------------------------------------------

def test_slack_focus_with_no_forced_state_is_no_op(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    assert slack.set_presence_calls == []
    assert slack.set_profile_status_calls == []
    assert slack.get_profile_status_calls == 0
    assert scheduler.scheduled == []
    assert fsm.snapshot.focus == FocusState.SLACK_FOCUSED


# ---------------------------------------------------------------------------
# Focus loss starts grace timer
# ---------------------------------------------------------------------------

def test_focus_loss_starts_grace_timer_with_configured_delay(setup):
    fsm, _, scheduler, _ = setup(grace_seconds=45)
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    assert len(scheduler.scheduled) == 1
    assert scheduler.scheduled[0][0] == 45
    assert fsm.snapshot.focus == FocusState.OTHER_FOCUSED_PENDING_AWAY


def test_focus_loss_when_disabled_does_not_schedule(setup):
    fsm, _, scheduler, _ = setup(enabled=False)
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    assert scheduler.scheduled == []


def test_repeated_non_slack_activations_do_not_schedule_more_timers(setup):
    fsm, _, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    fsm.on_window_activated("konsole")
    fsm.on_window_activated("vivaldi-stable")
    assert len(scheduler.scheduled) == 1


# ---------------------------------------------------------------------------
# Grace expiry applies forced state
# ---------------------------------------------------------------------------

def test_grace_expiry_calls_both_apis(setup):
    fsm, slack, scheduler, clock = setup(
        status_text="Heads down", status_emoji=":dart:", status_safety_buffer_seconds=3600,
    )
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()

    assert slack.set_presence_calls == ["away"]
    assert len(slack.set_profile_status_calls) == 1
    text, emoji, expiration = slack.set_profile_status_calls[0]
    assert text == "Heads down"
    assert emoji == ":dart:"
    assert expiration == int(clock.now) + 3600
    snap = fsm.snapshot
    assert snap.focus == FocusState.OTHER_FOCUSED
    assert snap.we_forced_away is True
    assert snap.we_forced_status is True


def test_grace_expiry_when_disabled_meanwhile_does_nothing(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    fsm.set_enabled(False)
    # Scheduler still has the handle (because cancellation happens in set_enabled);
    # but if a stale callback somehow fires, it should be a no-op.
    assert scheduler.scheduled == []


# ---------------------------------------------------------------------------
# Focus return cancels timer / clears forced state
# ---------------------------------------------------------------------------

def test_focus_return_within_grace_cancels_no_api_calls(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    fsm.on_window_activated("Slack")
    assert scheduler.scheduled == []
    assert slack.set_presence_calls == []
    assert slack.set_profile_status_calls == []


def test_focus_return_after_grace_clears_both(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()  # apply forced state
    assert fsm.snapshot.we_forced_away
    assert fsm.snapshot.we_forced_status

    fsm.on_window_activated("Slack")  # focus return
    # Should: get_profile_status, set_profile_status('','',0), set_presence('auto')
    assert slack.get_profile_status_calls == 1
    assert slack.set_profile_status_calls == [
        ("Heads down", ":dart:", pytest.approx(slack.set_profile_status_calls[0][2])),
        ("", "", 0),
    ]
    assert slack.set_presence_calls == ["away", "auto"]
    assert fsm.snapshot.we_forced_away is False
    assert fsm.snapshot.we_forced_status is False


def test_user_changed_status_is_not_clobbered_on_focus_return(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()  # we set "Heads down"

    # User edits their status manually while we're away.
    slack.profile_status = ProfileStatus(text="In a meeting", emoji=":calendar:", expiration=0)

    fsm.on_window_activated("Slack")
    # Should NOT have called set_profile_status to clear
    assert slack.set_profile_status_calls == [("Heads down", ":dart:", pytest.approx(slack.set_profile_status_calls[0][2]))]
    # But presence-clearing still runs
    assert slack.set_presence_calls == ["away", "auto"]
    # Internal flag dropped (we no longer believe we own the status)
    assert fsm.snapshot.we_forced_status is False


def test_get_profile_failure_blocks_status_clear(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()

    # Simulate scope removal between apply and clear
    slack.get_profile_response = ApiHealth(ok=False, error="missing_scope", needed_scope="users.profile:read")

    fsm.on_window_activated("Slack")
    # Did NOT call set_profile_status to clear (only the original apply call)
    assert len(slack.set_profile_status_calls) == 1
    # Presence clear still ran (independent of status path)
    assert slack.set_presence_calls == ["away", "auto"]
    # we_forced_status stays True (we couldn't verify what to do)
    assert fsm.snapshot.we_forced_status is True


# ---------------------------------------------------------------------------
# Disable / enable
# ---------------------------------------------------------------------------

def test_disable_when_forced_clears_state(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()

    fsm.set_enabled(False)
    assert slack.set_presence_calls == ["away", "auto"]
    assert slack.set_profile_status_calls[-1] == ("", "", 0)
    assert fsm.snapshot.enabled is False


def test_disable_when_pending_cancels_timer_no_api_calls(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    fsm.set_enabled(False)
    assert scheduler.scheduled == []
    assert slack.set_presence_calls == []


def test_disable_when_clean_does_no_api_calls(setup):
    fsm, slack, _, _ = setup()
    fsm.set_enabled(False)
    assert slack.set_presence_calls == []
    assert slack.set_profile_status_calls == []


def test_redundant_set_enabled_is_noop(setup):
    fsm, slack, _, _ = setup()
    fsm.set_enabled(True)  # already enabled
    assert slack.set_presence_calls == []


def test_disabled_state_machine_ignores_focus_events(setup):
    fsm, slack, scheduler, _ = setup(enabled=False)
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next() if scheduler.scheduled else None  # nothing should be scheduled
    assert slack.set_presence_calls == []
    assert slack.set_profile_status_calls == []


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

def test_shutdown_clears_forced_state(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()

    fsm.shutdown()
    assert slack.set_presence_calls == ["away", "auto"]
    assert slack.set_profile_status_calls[-1] == ("", "", 0)


def test_shutdown_when_clean_is_noop(setup):
    fsm, slack, _, _ = setup()
    fsm.shutdown()
    assert slack.set_presence_calls == []


def test_shutdown_cancels_pending_timer(setup):
    fsm, _, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    fsm.shutdown()
    assert scheduler.scheduled == []


# ---------------------------------------------------------------------------
# Partial failure behavior
# ---------------------------------------------------------------------------

def test_apply_when_setpresence_fails_does_not_set_we_forced_away(setup):
    fsm, slack, scheduler, _ = setup()
    slack.set_presence_response = ApiHealth(ok=False, error="server_error")
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()
    assert fsm.snapshot.we_forced_away is False
    # But the status set still ran and may have succeeded
    assert fsm.snapshot.we_forced_status is True


def test_apply_when_status_set_fails_does_not_set_we_forced_status(setup):
    fsm, slack, scheduler, _ = setup()
    slack.set_profile_response = ApiHealth(ok=False, error="server_error")
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()
    assert fsm.snapshot.we_forced_away is True  # presence call independent
    assert fsm.snapshot.we_forced_status is False


# ---------------------------------------------------------------------------
# Internal-transition observer (grace-expiry hook)
# ---------------------------------------------------------------------------

def test_grace_expiry_invokes_observer_with_prev_snapshot(setup_with_observer):
    fsm, slack, scheduler, _, observed = setup_with_observer()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    assert observed == []  # not triggered yet

    scheduler.fire_next()  # grace expires -> apply forced state
    assert len(observed) == 1
    result, prev, label = observed[0]
    assert label == "grace_expired"
    # prev_snapshot was captured BEFORE _apply_forced_state ran; flags False
    assert prev.we_forced_away is False
    assert prev.we_forced_status is False
    # result reflects the API calls
    assert result.presence_call is not None and result.presence_call.ok
    assert result.status_set_call is not None and result.status_set_call.ok


def test_grace_expiry_observer_not_called_when_disabled(setup_with_observer):
    fsm, _, scheduler, _, observed = setup_with_observer()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    fsm.set_enabled(False)  # cancels timer; observer not invoked
    assert observed == []


def test_observer_not_called_for_method_driven_transitions(setup_with_observer):
    """Public-method transitions return the result directly, so the
    observer is reserved for grace-expiry only."""
    fsm, _, scheduler, _, observed = setup_with_observer()
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    fsm.on_window_activated("Slack")  # within grace, cancels
    assert observed == []


def test_observer_optional_default_no_callback(setup):
    """Observer parameter is optional; FSMs built without one still work."""
    fsm, _, scheduler, _ = setup()  # no observer argument
    fsm.on_window_activated("Slack")
    fsm.on_window_activated("firefox")
    scheduler.fire_next()
    # Did not crash; that's the test.


# ---------------------------------------------------------------------------
# Rapid alt-tab flapping
# ---------------------------------------------------------------------------

def test_rapid_alt_tab_flapping_cancels_each_pending(setup):
    fsm, slack, scheduler, _ = setup()
    fsm.on_window_activated("Slack")
    for _ in range(5):
        fsm.on_window_activated("firefox")
        fsm.on_window_activated("Slack")
    # Final state: focused on Slack, no scheduled timer, no API calls
    assert scheduler.scheduled == []
    assert slack.set_presence_calls == []
    assert slack.set_profile_status_calls == []
