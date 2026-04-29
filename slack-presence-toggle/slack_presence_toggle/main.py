"""Entry point: wires SlackClient + state machine + D-Bus listener + tray UI.

Run with: python3 -m slack_presence_toggle  (also see top-level slack_presence_toggle.py)
"""
from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtDBus import QDBusConnection, QDBusInterface
from PyQt6.QtWidgets import QApplication

from .config import DEFAULT_CONFIG_PATH, Config
from .focus_listener import FocusListener
from .notifications import Urgency, notify
from .qt_scheduler import QtScheduler
from .slack_client import ApiHealth, SlackClient
from .state_machine import FocusStateMachine, TransitionResult
from .tray import TrayApp

log = logging.getLogger(__name__)


KWIN_SCRIPT_NAME = "slack-focus-monitor"
KWIN_SCRIPT_PATH = (
    Path.home() / ".local/share/kwin/scripts" / KWIN_SCRIPT_NAME / "contents/code/main.js"
)
KWIN_HEALTH_CHECK_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes


class Application(QObject):
    def __init__(self, qapp: QApplication, *, config_path: Path = DEFAULT_CONFIG_PATH):
        super().__init__()
        self._qapp = qapp
        self._config_path = config_path
        self._config = Config.load(config_path)

        self._token = self._read_token()
        self._slack = SlackClient(self._token, timeout=10.0) if self._token else None
        self._scheduler = QtScheduler(self)
        self._fsm: FocusStateMachine | None = None  # built once Slack is wired
        self._listener = FocusListener(self)
        self._listener.window_activated.connect(self._on_window_activated)

        self._tray = TrayApp(config=self._config, parent=self)
        self._tray.enable_toggle_requested.connect(self._on_enable_toggle)
        self._tray.reload_token_requested.connect(self._on_reload_token)
        self._tray.reload_kwin_script_requested.connect(self._on_reload_kwin_script)
        self._tray.config_change_requested.connect(self._on_config_change)
        self._tray.quit_requested.connect(self._on_quit)
        self._tray.set_pre_show_refresh(self._refresh_status)

        self._health = ApiHealth.success()

    # ------------------------------------------------------------- lifecycle
    def start(self) -> int:
        if not self._listener.register():
            log.error("D-Bus listener could not register; another instance running?")
            notify(
                "Slack Presence Toggle",
                "Another instance is already running, or D-Bus is unavailable.",
                urgency=Urgency.CRITICAL,
            )
            return 1

        self._tray.show()

        if self._token is None:
            self._handle_health(ApiHealth(ok=False, error="missing_token"))
        else:
            self._initial_auth_check()

        # Bring KWin script into a state where it immediately re-emits the
        # current focus to us. Best-effort; safe to fail (script may not be
        # installed yet).
        QTimer.singleShot(500, self._reload_kwin_script_for_initial_focus)

        # Periodic auto-heal: if KWin restarts (Plasma update / crash / log
        # out and back in) it sometimes drops loaded scripts even when the
        # kwinrc Plugins entry is intact. The check + reload is cheap.
        self._kwin_health_timer = QTimer(self)
        self._kwin_health_timer.timeout.connect(self._kwin_health_tick)
        self._kwin_health_timer.start(KWIN_HEALTH_CHECK_INTERVAL_MS)

        return self._qapp.exec()

    def _initial_auth_check(self) -> None:
        assert self._slack is not None
        health, info = self._slack.auth_test()
        self._handle_health(health)
        if health.ok and info:
            self._tray.update_user(info.user, info.team)
            self._build_fsm()
            self._refresh_status()

    def _build_fsm(self) -> None:
        assert self._slack is not None
        self._fsm = FocusStateMachine(
            slack=self._slack,
            scheduler=self._scheduler,
            config=self._config,
            on_internal_transition=self._on_internal_transition,
        )
        # Push initial snapshot to tray so menu shows enabled/disabled state.
        self._tray.update_state(
            snapshot=self._fsm.snapshot, presence=None, profile=None
        )

    # -------------------------------------------------------------- handlers
    def _on_window_activated(self, resource_class: str, caption: str) -> None:
        if self._fsm is None:
            return
        prev = self._fsm.snapshot
        result = self._fsm.on_window_activated(resource_class)
        self._after_transition(result, prev_snapshot=prev, label=resource_class)

    def _on_internal_transition(self, result, prev_snapshot, label: str) -> None:
        """Hook for FSM-internal transitions (currently only grace-expiry)."""
        self._after_transition(result, prev_snapshot=prev_snapshot, label=label)

    def _on_reload_kwin_script(self) -> None:
        """Tray-menu-triggered KWin script reload (manual recovery)."""
        log.info("user-requested KWin script reload")
        self._reload_kwin_script_for_initial_focus()
        # Confirm to the user that something happened, since the action
        # otherwise has no visible feedback.
        if self._is_kwin_script_loaded():
            notify(
                "Slack Presence Toggle",
                "KWin focus monitor reloaded.",
                urgency=Urgency.LOW,
                icon="dialog-ok",
                tray=self._tray.system_tray,
            )

    def _on_enable_toggle(self, enabled: bool) -> None:
        if self._fsm is None:
            return
        prev = self._fsm.snapshot
        result = self._fsm.set_enabled(enabled)
        self._config.enabled = enabled
        self._save_config()
        self._after_transition(result, prev_snapshot=prev, label="quick-disable" if not enabled else "quick-enable")
        if enabled:
            # Trigger fresh KWin event so the new state syncs to current focus.
            self._reload_kwin_script_for_initial_focus()

    def _on_reload_token(self) -> None:
        new_token = self._read_token()
        if new_token is None:
            self._handle_health(ApiHealth(ok=False, error="missing_token"))
            return
        self._token = new_token
        if self._slack is None:
            self._slack = SlackClient(self._token, timeout=10.0)
        else:
            self._slack._token = self._token  # SlackClient is small; in-place is fine
        health, info = self._slack.auth_test()
        self._handle_health(health)
        if health.ok and info:
            self._tray.update_user(info.user, info.team)
            if self._fsm is None:
                self._build_fsm()
            notify(
                "Slack Presence Toggle",
                f"Token reloaded — authenticated as {info.user} @ {info.team}",
                urgency=Urgency.LOW, icon="dialog-ok",
                tray=self._tray.system_tray,
            )

    def _on_config_change(self, field: str, value) -> None:
        if not hasattr(self._config, field):
            log.warning("ignored unknown config field %r", field)
            return
        setattr(self._config, field, value)
        self._save_config()
        self._tray.update_config(self._config)
        log.info("config updated: %s = %r", field, value)

    def _on_quit(self) -> None:
        if self._fsm is not None:
            self._fsm.shutdown()
        self._listener.unregister()
        self._qapp.quit()

    # ------------------------------------------------------- post-transition
    def _after_transition(self, result: TransitionResult, *, prev_snapshot, label: str) -> None:
        # Fold all API healths into a single representative health.
        worst = self._fold_health(result)
        if worst is not None:
            self._handle_health(worst)

        # Refresh status after any API call (always best-effort).
        self._refresh_status()

        # Maybe notify
        if self._fsm is None:
            return
        snap = self._fsm.snapshot
        self._maybe_notify_transition(prev_snapshot, snap, label, result)

    def _fold_health(self, result: TransitionResult) -> ApiHealth | None:
        for h in (result.presence_call, result.status_set_call, result.status_clear_call):
            if h is not None and not h.ok:
                return h
        for h in (result.presence_call, result.status_set_call, result.status_clear_call):
            if h is not None and h.ok:
                return h
        return None

    def _refresh_status(self) -> None:
        if self._slack is None or self._fsm is None:
            return
        ph_health, presence = self._slack.get_presence()
        sh_health, profile = self._slack.get_profile_status()
        # If either read fails with auth, surface; otherwise keep prior health.
        if not ph_health.ok and ph_health.error in ("invalid_auth", "token_revoked", "missing_scope"):
            self._handle_health(ph_health)
        elif not sh_health.ok and sh_health.error in ("invalid_auth", "token_revoked", "missing_scope"):
            self._handle_health(sh_health)
        self._tray.update_state(
            snapshot=self._fsm.snapshot,
            presence=presence,
            profile=profile,
        )

    def _handle_health(self, health: ApiHealth) -> None:
        was_ok = self._health.ok
        was_error = self._health.error
        self._health = health
        self._tray.update_health(health)

        # Notify on transitions only (not every poll).
        if was_ok and not health.ok and health.error in (
            "invalid_auth", "token_revoked", "account_inactive", "missing_scope", "missing_token"
        ):
            self._notify_critical_health(health)
        elif (not was_ok) and health.ok:
            notify(
                "Slack Presence Toggle",
                "API connection restored.",
                urgency=Urgency.LOW, icon="dialog-ok",
                tray=self._tray.system_tray,
            )
        elif (not was_ok) and was_error != health.error and not health.ok:
            # Health worsened to a different failure mode; notify.
            self._notify_critical_health(health)

    def _notify_critical_health(self, health: ApiHealth) -> None:
        if health.error == "missing_scope":
            body = (
                f"The OAuth token is missing the {health.needed_scope!r} scope. "
                "Add it in the Slack app config and reinstall, then click "
                "'Reload token from file'."
            )
        elif health.error in ("invalid_auth", "token_revoked"):
            body = (
                "The OAuth token is no longer valid. Generate a new token in "
                "Slack and overwrite ~/.config/slack-presence-toggle/token, "
                "then click 'Reload token from file'."
            )
        elif health.error == "missing_token":
            body = (
                "Token file is missing. Place a User OAuth Token at "
                "~/.config/slack-presence-toggle/token and click "
                "'Reload token from file'."
            )
        else:
            body = f"API error: {health.error}"
        notify(
            "Slack Presence Toggle — attention",
            body,
            urgency=Urgency.CRITICAL,
            icon="dialog-error",
            tray=self._tray.system_tray,
        )

    def _maybe_notify_transition(self, prev_snapshot, new_snapshot, label, result) -> None:
        if not self._config.notifications:
            return
        # Fire only when our forced state actually changed.
        prev_forced = prev_snapshot.we_forced_away or prev_snapshot.we_forced_status
        new_forced = new_snapshot.we_forced_away or new_snapshot.we_forced_status
        if prev_forced == new_forced:
            return  # no transition, no notify
        if new_forced:
            body = f"Slack: Away — focus left Slack for {self._config.grace_seconds}s"
            notify("Slack Presence Toggle", body, urgency=Urgency.LOW,
                   icon="user-away", tray=self._tray.system_tray)
        else:
            if label == "quick-disable":
                body = "Slack: Active — auto-presence disabled"
            else:
                body = "Slack: Active — focus returned to Slack"
            notify("Slack Presence Toggle", body, urgency=Urgency.LOW,
                   icon="user-online", tray=self._tray.system_tray)

    # ------------------------------------------------------------------ I/O
    def _read_token(self) -> str | None:
        token_path = Path(self._config.token_file).expanduser()
        if not token_path.exists():
            log.warning("token file %s not found", token_path)
            return None
        token = token_path.read_text(encoding="utf-8").strip()
        if not token.startswith("xoxp-"):
            log.warning("token in %s does not start with xoxp-", token_path)
            return None
        return token

    def _save_config(self) -> None:
        try:
            self._config.save(self._config_path)
        except Exception as e:
            log.warning("could not save config: %s", e)

    # ----------------------------------------------------- KWin script ops
    def _kwin_scripting_iface(self) -> QDBusInterface | None:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return None
        iface = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", bus)
        return iface if iface.isValid() else None

    def _is_kwin_script_loaded(self, iface: QDBusInterface | None = None) -> bool:
        iface = iface or self._kwin_scripting_iface()
        if iface is None:
            return False
        reply = iface.call("isScriptLoaded", KWIN_SCRIPT_NAME)
        args = reply.arguments() if reply is not None else None
        return bool(args[0]) if args else False

    def _load_kwin_script(self, iface: QDBusInterface) -> None:
        iface.call("loadScript", str(KWIN_SCRIPT_PATH), KWIN_SCRIPT_NAME)
        iface.call("start")

    def _ensure_kwin_script_loaded(self, *, notify_on_recovery: bool = True) -> bool:
        """Load the KWin script if it's currently unloaded.

        Returns True if the script is loaded after this call, False if it
        could not be loaded (D-Bus down, files missing, etc).
        """
        iface = self._kwin_scripting_iface()
        if iface is None:
            return False
        if self._is_kwin_script_loaded(iface):
            return True
        if not KWIN_SCRIPT_PATH.exists():
            log.warning(
                "KWin script files missing at %s; run kwin-script/install.sh",
                KWIN_SCRIPT_PATH,
            )
            return False
        log.info("KWin script not loaded; auto-loading from %s", KWIN_SCRIPT_PATH)
        self._load_kwin_script(iface)
        if notify_on_recovery:
            notify(
                "Slack Presence Toggle",
                "Reconnected to KWin focus monitor.",
                urgency=Urgency.LOW,
                icon="dialog-ok",
                tray=self._tray.system_tray,
            )
        return True

    def _reload_kwin_script_for_initial_focus(self) -> None:
        """Force KWin to re-fire windowActivated for the current focus.

        Auto-loads the script if it's not currently loaded (handles the case
        where KWin restarted between sessions and didn't pick the script
        back up despite the kwinrc Plugins entry).
        """
        iface = self._kwin_scripting_iface()
        if iface is None:
            log.debug("KWin Scripting interface unavailable; skipping reload")
            return
        if not KWIN_SCRIPT_PATH.exists():
            log.warning(
                "KWin script files missing at %s; run kwin-script/install.sh",
                KWIN_SCRIPT_PATH,
            )
            notify(
                "Slack Presence Toggle — KWin script missing",
                f"Files not found at {KWIN_SCRIPT_PATH}. "
                "Run kwin-script/install.sh from the project root.",
                urgency=Urgency.CRITICAL,
                icon="dialog-error",
                tray=self._tray.system_tray,
            )
            return
        # Unload (if loaded) + load forces re-execution of the script body,
        # which immediately emits a windowActivated event for the current
        # focus.
        if self._is_kwin_script_loaded(iface):
            iface.call("unloadScript", KWIN_SCRIPT_NAME)
        self._load_kwin_script(iface)

    def _kwin_health_tick(self) -> None:
        """Periodic timer callback. Auto-recovers if the script unloaded."""
        if self._fsm is None or not self._fsm.snapshot.enabled:
            return
        self._ensure_kwin_script_loaded(notify_on_recovery=True)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("slack-presence-toggle")
    qapp.setDesktopFileName("slack-presence-toggle")
    qapp.setQuitOnLastWindowClosed(False)

    application = Application(qapp)

    # Wake the Python interpreter periodically so signal handlers run
    # while Qt is in its C++ event loop. Without this, Ctrl+C / SIGTERM
    # are queued indefinitely.
    _signal_pump = QTimer()
    _signal_pump.start(500)
    _signal_pump.timeout.connect(lambda: None)

    def _on_signal(sig, frame):
        log.info("received signal %d, shutting down", sig)
        application._on_quit()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    return application.start()


if __name__ == "__main__":
    sys.exit(main())
