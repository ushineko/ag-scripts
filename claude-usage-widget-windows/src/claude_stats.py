"""Claude Code usage statistics parsing."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import structlog

from .config import get_claude_projects_dir, get_setting

log = structlog.get_logger(__name__)


def get_session_window(
    window_hours: int = None, reset_hour: int = None
) -> tuple[datetime, datetime]:
    """
    Calculate the current session window boundaries based on reset hour.
    Windows are aligned to the user's reset time (from Claude's /usage).

    For example, if reset_hour=2 and window_hours=4:
    - Windows are: 22:00-02:00, 02:00-06:00, 06:00-10:00, etc.

    Returns (window_start, window_end) as datetime objects in local timezone.
    """
    if window_hours is None:
        window_hours = get_setting("window_hours", 4)
    if reset_hour is None:
        reset_hour = get_setting("reset_hour", 2)

    now = datetime.now().astimezone()
    current_hour = now.hour

    # Calculate all window boundary hours in a day (aligned to reset_hour)
    # E.g., reset_hour=2, window_hours=4 → boundaries at [2, 6, 10, 14, 18, 22]
    boundaries = [
        (reset_hour + i * window_hours) % 24 for i in range(24 // window_hours)
    ]
    boundaries.sort()

    # Find which window we're in
    window_end_hour = None
    for boundary in boundaries:
        if current_hour < boundary:
            window_end_hour = boundary
            break

    # If we didn't find one, we're past the last boundary → next window is first boundary tomorrow
    if window_end_hour is None:
        window_end_hour = boundaries[0]
        # Window ends tomorrow
        window_end = now.replace(
            hour=window_end_hour, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
    else:
        window_end = now.replace(
            hour=window_end_hour, minute=0, second=0, microsecond=0
        )

    # Window start is window_hours before window end
    window_start = window_end - timedelta(hours=window_hours)

    log.debug(
        "session_window_calculated",
        window_hours=window_hours,
        reset_hour=reset_hour,
        current_hour=current_hour,
        boundaries=boundaries,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
    )

    return window_start, window_end


def get_time_until_reset(
    window_start: datetime, window_end: datetime
) -> tuple[str, str, int, int]:
    """
    Calculate time remaining until window resets, with window times displayed.

    Returns:
        tuple: (window_str, countdown_str, hours_remaining, minutes_remaining)
    """
    now = datetime.now().astimezone()
    delta = window_end - now

    # Format window times in 24H format
    start_time = window_start.strftime("%H:%M")
    end_time = window_end.strftime("%H:%M")
    window_str = f"{start_time} - {end_time}"

    if delta.total_seconds() <= 0:
        return window_str, "resetting...", 0, 0

    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)

    if hours > 0:
        countdown_str = f"{hours}h {minutes}m"
    else:
        countdown_str = f"{minutes}m"

    return window_str, countdown_str, hours, minutes


def get_claude_stats(
    window_start: datetime = None, window_end: datetime = None
) -> Optional[dict]:
    """
    Read and parse Claude Code usage from session files within the time window.
    If no window specified, uses all files modified today.

    Returns:
        dict with usage stats or None if no data found
    """
    projects_path = get_claude_projects_dir()
    log.info("scanning_projects_dir", path=str(projects_path), exists=projects_path.exists())

    if not projects_path.exists():
        log.warning("projects_dir_not_found", path=str(projects_path))
        return None

    try:
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_create = 0
        api_calls = 0
        files_processed = 0
        files_scanned = 0
        files_skipped_mtime = 0

        # Convert window times to timestamps for comparison
        if window_start and window_end:
            window_start_ts = window_start.timestamp()
            window_end_ts = window_end.timestamp()
            log.debug(
                "window_filter",
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
            )
        else:
            # Fallback: use today (UTC)
            today = datetime.now(timezone.utc).date()
            window_start_ts = None
            window_end_ts = None
            log.debug("window_filter_fallback", today=str(today))

        for root, dirs, files in os.walk(projects_path):
            for f in files:
                if f.endswith(".jsonl"):
                    files_scanned += 1
                    path = os.path.join(root, f)
                    file_mtime = os.path.getmtime(path)
                    file_mtime_dt = datetime.fromtimestamp(file_mtime)

                    # Filter by window if specified
                    if window_start_ts and window_end_ts:
                        # Skip files not modified within window
                        if file_mtime < window_start_ts or file_mtime > window_end_ts:
                            files_skipped_mtime += 1
                            log.debug(
                                "file_skipped_mtime",
                                file=path,
                                mtime=file_mtime_dt.isoformat(),
                            )
                            continue
                    else:
                        # Fallback: only files modified today
                        mtime_date = datetime.fromtimestamp(
                            file_mtime, tz=timezone.utc
                        ).date()
                        if mtime_date != today:
                            files_skipped_mtime += 1
                            continue

                    files_processed += 1
                    file_api_calls = 0
                    file_tokens = 0

                    log.debug("processing_file", file=path, mtime=file_mtime_dt.isoformat())

                    # Parse this session file, filtering by timestamp if needed
                    try:
                        with open(path, "r", encoding="utf-8") as fp:
                            for line_num, line in enumerate(fp, 1):
                                try:
                                    data = json.loads(line)

                                    # Check timestamp if window filtering
                                    if window_start_ts and window_end_ts:
                                        msg_ts = data.get("timestamp")
                                        if msg_ts:
                                            try:
                                                msg_time = datetime.fromisoformat(
                                                    msg_ts.replace("Z", "+00:00")
                                                )
                                                msg_timestamp = msg_time.timestamp()
                                                if (
                                                    msg_timestamp < window_start_ts
                                                    or msg_timestamp > window_end_ts
                                                ):
                                                    continue
                                            except (ValueError, AttributeError):
                                                pass

                                    if "message" in data and isinstance(
                                        data["message"], dict
                                    ):
                                        usage = data["message"].get("usage", {})
                                        if usage:
                                            api_calls += 1
                                            file_api_calls += 1
                                            input_t = usage.get("input_tokens", 0)
                                            output_t = usage.get("output_tokens", 0)
                                            total_input += input_t
                                            total_output += output_t
                                            file_tokens += input_t + output_t
                                            total_cache_read += usage.get(
                                                "cache_read_input_tokens", 0
                                            )
                                            total_cache_create += usage.get(
                                                "cache_creation_input_tokens", 0
                                            )
                                except json.JSONDecodeError as e:
                                    log.debug(
                                        "json_decode_error",
                                        file=path,
                                        line=line_num,
                                        error=str(e),
                                    )

                        log.debug(
                            "file_processed",
                            file=path,
                            api_calls=file_api_calls,
                            tokens=file_tokens,
                        )

                    except (IOError, OSError) as e:
                        log.warning("file_read_error", file=path, error=str(e))

        log.info(
            "scan_complete",
            files_scanned=files_scanned,
            files_processed=files_processed,
            files_skipped_mtime=files_skipped_mtime,
            total_api_calls=api_calls,
            total_tokens=total_input + total_output,
        )

        if files_processed == 0:
            log.warning("no_files_processed")
            return None

        result = {
            "session_tokens": total_input + total_output,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read": total_cache_read,
            "cache_create": total_cache_create,
            "api_calls": api_calls,
            "files_processed": files_processed,
            "window_start": window_start,
            "window_end": window_end,
        }

        log.info("stats_result", **{k: v for k, v in result.items() if k not in ("window_start", "window_end")})
        return result

    except Exception as e:
        log.exception("stats_error", error=str(e))
        return None


def format_tokens(tokens: int) -> str:
    """Format token count with k/M suffix for readability."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    elif tokens >= 1_000:
        return f"{tokens / 1_000:.1f}k"
    else:
        return str(tokens)


def calculate_usage_percentage(
    session_tokens: int, budget: int = None, offset: int = None
) -> float:
    """Calculate usage percentage with optional offset adjustment."""
    if budget is None:
        budget = get_setting("session_budget", 500000)
    if offset is None:
        offset = get_setting("token_offset", 0)

    adjusted_tokens = session_tokens + offset
    if budget <= 0:
        return 0.0
    percentage = min(100.0, (adjusted_tokens / budget) * 100)

    log.debug(
        "usage_percentage",
        session_tokens=session_tokens,
        offset=offset,
        adjusted_tokens=adjusted_tokens,
        budget=budget,
        percentage=percentage,
    )

    return percentage


def get_usage_color(percentage: float) -> str:
    """Get color based on usage percentage."""
    if percentage < 50:
        return "green"
    elif percentage < 80:
        return "yellow"
    else:
        return "red"
