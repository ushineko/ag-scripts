from __future__ import annotations

import logging
import subprocess
from enum import Enum
from typing import Optional

from PyQt6.QtWidgets import QSystemTrayIcon

log = logging.getLogger(__name__)

APP_NAME = "Slack Presence Toggle"


class Urgency(Enum):
    LOW = "low"
    NORMAL = "normal"
    CRITICAL = "critical"


def notify(
    title: str,
    body: str,
    *,
    icon: Optional[str] = None,
    urgency: Urgency = Urgency.LOW,
    tray: Optional[QSystemTrayIcon] = None,
) -> None:
    """Fire a desktop notification via tray + notify-send.

    Mirrors the foghorn-leghorn pattern: tray.showMessage if a tray is
    visible, plus a fire-and-forget `notify-send` for richer KDE delivery.
    Failures are swallowed; this is best-effort.
    """
    if tray is not None and tray.isVisible():
        msg_icon = QSystemTrayIcon.MessageIcon.Information
        if urgency == Urgency.NORMAL:
            msg_icon = QSystemTrayIcon.MessageIcon.Warning
        elif urgency == Urgency.CRITICAL:
            msg_icon = QSystemTrayIcon.MessageIcon.Critical
        tray.showMessage(title, body, msg_icon, 5000)

    cmd = ["notify-send", f"--app-name={APP_NAME}", f"--urgency={urgency.value}"]
    if icon:
        cmd.append(f"--icon={icon}")
    cmd.extend([title, body])
    try:
        subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        log.debug("notify-send not installed; skipping")
    except Exception as e:
        log.warning("notify-send failed: %s", e)
