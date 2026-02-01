"""
Utility functions and shared constants for VPN Toggle
"""
import logging
from datetime import datetime
from pathlib import Path


def setup_logging(log_file: str = None, level: str = "INFO") -> logging.Logger:
    """
    Setup logging to file and console.

    Args:
        log_file: Path to log file (will be expanded if contains ~)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Logger instance
    """
    if log_file is None:
        log_file = "~/.config/vpn-toggle/vpn-toggle.log"

    log_path = Path(log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Setup root logger
    logger = logging.getLogger('vpn_toggle')
    logger.setLevel(getattr(logging, level.upper()))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def format_timestamp(dt: datetime) -> str:
    """
    Format datetime for display.

    Args:
        dt: Datetime object

    Returns:
        Formatted timestamp string
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_config_dir() -> Path:
    """
    Get the configuration directory path.

    Returns:
        Path to ~/.config/vpn-toggle/
    """
    config_dir = Path.home() / ".config" / "vpn-toggle"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file() -> Path:
    """
    Get the configuration file path.

    Returns:
        Path to ~/.config/vpn-toggle/config.json
    """
    return get_config_dir() / "config.json"
