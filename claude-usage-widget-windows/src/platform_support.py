"""Platform detection for the Claude Usage Widget.

Single source of truth for OS branching. All platform-specific code (config /
log path resolution, packaging) routes through these constants instead of
open-coding `sys.platform` checks, mirroring the sibling `vscode-launcher`
project's pattern.
"""

import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
