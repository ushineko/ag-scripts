from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .config import Config
from .slack_client import ApiHealth, SlackClient

log = logging.getLogger(__name__)


class FocusState(Enum):
    SLACK_FOCUSED = "slack_focused"
    OTHER_FOCUSED = "other_focused"
    OTHER_FOCUSED_PENDING_AWAY = "other_focused_pending_away"


class Scheduler(Protocol):
    def schedule(self, delay_seconds: float, callback: Callable[[], None]) -> object: ...
    def cancel(self, handle: object) -> None: ...


@dataclass(frozen=True)
class StateSnapshot:
    enabled: bool
    focus: FocusState
    we_forced_away: bool
    we_forced_status: bool


@dataclass(frozen=True)
class TransitionResult:
    presence_call: ApiHealth | None = None
    status_set_call: ApiHealth | None = None
    status_clear_call: ApiHealth | None = None

    @property
    def all_ok(self) -> bool:
        return all(h is None or h.ok for h in (
            self.presence_call, self.status_set_call, self.status_clear_call
        ))


class FocusStateMachine:
    """Pure focus -> Slack-presence orchestration.

    Owns:
      - focus state (slack_focused / pending / other_focused)
      - we_forced_away / we_forced_status flags (so we never clobber a
        user-set status or a manual presence toggle)
      - the grace-period timer

    Calls into:
      - SlackClient (for set/get presence and profile status)
      - Scheduler (for the grace timer)

    Does NOT own:
      - D-Bus listening (caller forwards window-activated events here)
      - UI / notifications (caller subscribes to TransitionResult returns)
    """

    def __init__(
        self,
        *,
        slack: SlackClient,
        scheduler: Scheduler,
        config: Config,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._slack = slack
        self._scheduler = scheduler
        self._config = config
        self._clock = clock

        self._enabled = config.enabled
        self._focus = FocusState.OTHER_FOCUSED  # conservative: assume not in Slack
        self._we_forced_away = False
        self._we_forced_status = False
        self._grace_handle: object | None = None

    @property
    def snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            enabled=self._enabled,
            focus=self._focus,
            we_forced_away=self._we_forced_away,
            we_forced_status=self._we_forced_status,
        )

    def on_window_activated(self, resource_class: str) -> TransitionResult:
        is_slack = (resource_class == self._config.slack_resource_class)
        if is_slack:
            return self._handle_slack_focus()
        return self._handle_other_focus()

    def _handle_slack_focus(self) -> TransitionResult:
        self._cancel_grace_timer()
        prev_focus = self._focus
        self._focus = FocusState.SLACK_FOCUSED

        if not self._enabled:
            return TransitionResult()
        # No need to clear if nothing was forced.
        if not (self._we_forced_away or self._we_forced_status):
            return TransitionResult()
        # If we were just briefly pending and never applied, also nothing to clear.
        if prev_focus == FocusState.OTHER_FOCUSED_PENDING_AWAY and not (
            self._we_forced_away or self._we_forced_status
        ):
            return TransitionResult()
        return self._clear_forced_state()

    def _handle_other_focus(self) -> TransitionResult:
        if self._focus == FocusState.SLACK_FOCUSED:
            self._focus = FocusState.OTHER_FOCUSED_PENDING_AWAY
            if self._enabled:
                self._grace_handle = self._scheduler.schedule(
                    self._config.grace_seconds, self._on_grace_expired
                )
        # Already pending or other_focused: nothing to do.
        return TransitionResult()

    def _on_grace_expired(self) -> None:
        self._grace_handle = None
        # The caller may have changed focus or disabled us between schedule
        # and fire; re-check.
        if self._focus != FocusState.OTHER_FOCUSED_PENDING_AWAY:
            return
        self._focus = FocusState.OTHER_FOCUSED
        if not self._enabled:
            return
        result = self._apply_forced_state()
        log.info("grace expired -> applied forced state: %s", result)

    def _apply_forced_state(self) -> TransitionResult:
        presence_health = self._slack.set_presence("away")
        if presence_health.ok:
            self._we_forced_away = True

        expiration = int(self._clock()) + self._config.status_safety_buffer_seconds
        status_health = self._slack.set_profile_status(
            self._config.status_text, self._config.status_emoji, expiration
        )
        if status_health.ok:
            self._we_forced_status = True

        return TransitionResult(
            presence_call=presence_health,
            status_set_call=status_health,
        )

    def _clear_forced_state(self) -> TransitionResult:
        result = TransitionResult()
        # Clear status first so a user looking at their Slack sees the
        # "Heads down" tag disappear before presence flips, which is the
        # less jarring order.
        if self._we_forced_status:
            health, current = self._slack.get_profile_status()
            if health.ok and current is not None:
                if current.text == self._config.status_text:
                    clear_health = self._slack.set_profile_status("", "", 0)
                    result = TransitionResult(
                        status_clear_call=clear_health,
                    )
                    if clear_health.ok:
                        self._we_forced_status = False
                else:
                    # User changed status while we were away; respect it.
                    log.info(
                        "user-set status %r differs from ours %r; not clearing",
                        current.text, self._config.status_text,
                    )
                    self._we_forced_status = False
            else:
                # Could not read profile (e.g., scope error). Don't clear blindly.
                result = TransitionResult(status_clear_call=health)

        if self._we_forced_away:
            presence_health = self._slack.set_presence("auto")
            if presence_health.ok:
                self._we_forced_away = False
            result = TransitionResult(
                presence_call=presence_health,
                status_set_call=result.status_set_call,
                status_clear_call=result.status_clear_call,
            )

        return result

    def _cancel_grace_timer(self) -> None:
        if self._grace_handle is not None:
            self._scheduler.cancel(self._grace_handle)
            self._grace_handle = None

    def set_enabled(self, enabled: bool) -> TransitionResult:
        if enabled == self._enabled:
            return TransitionResult()
        self._enabled = enabled
        if not enabled:
            self._cancel_grace_timer()
            return self._clear_forced_state()
        # Becoming enabled: caller is expected to trigger a fresh
        # windowActivated event so the state machine syncs to current focus.
        return TransitionResult()

    def shutdown(self) -> TransitionResult:
        """Best-effort cleanup. Always cancels timer; releases forced state."""
        self._cancel_grace_timer()
        if self._we_forced_away or self._we_forced_status:
            return self._clear_forced_state()
        return TransitionResult()
