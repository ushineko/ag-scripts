---
description: Create or update an uninstall script to remove artifacts (desktop files, configs).
---

1.  **Check for Existing Uninstaller**:
    -   Look for `uninstall.sh`, `remove.sh`, or similar in the project root.

2.  **Define Cleanup Scope**:
    -   Identify all system modifications made by the install script or the program itself. Common items:
        -   `.desktop` files in `~/.local/share/applications/`
        -   KWin rules in `~/.config/kwinrulesrc` (requires script to remove specific sections)
        -   Symlinks in `~/bin` or `/usr/local/bin`
        -   Systemd user units in `~/.config/systemd/user/`
        -   Cron jobs
        -   Autostart entries

3.  **Create/Update Script**:
    -   **Create**: If no script exists, create `uninstall.sh`.
    -   **Update**: If it exists, ensure it covers all items identified in the Scope.
    -   **Content**:
        -   The script should be idempotent (use `rm -f`, check if files exist before trying to delete).
        -   For KWin rules: If the install script added rules, the uninstaller should ideally remove them (or warn the user).
        -   Print clear messages ("Removing X...", "Done.").

4.  **Make Executable**:
    -   Run `chmod +x uninstall.sh`.

5.  **Verify**:
    -   (Optional but recommended) Run the uninstaller and verify key files are gone, then re-run installer to ensure clean state.
