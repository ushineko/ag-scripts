import subprocess


class HeadsetController:
    """Handles interaction with headsetcontrol for SteelSeries devices."""

    @staticmethod
    def get_battery_status() -> str | None:
        """Returns battery percentage string (e.g. '87%') or None if disconnected/error."""
        try:
            result = subprocess.run(
                ['headsetcontrol', '-b', '-c'],
                capture_output=True, text=True, check=True
            )
            output = result.stdout.strip()
            if output:
                try:
                    val = int(output)
                    if val < 0:
                        return None
                    return f"{val}%"
                except ValueError:
                    return None
            return None
        except Exception:
            return None

    @staticmethod
    def set_inactive_time(minutes: int) -> bool:
        """Sets the inactive time (disconnect on idle). minutes: 0 to disable, or 1-90."""
        try:
            subprocess.run(
                ['headsetcontrol', '-i', str(minutes)],
                capture_output=True, text=True, check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error setting inactive time: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error setting inactive time: {e}")
            return False
