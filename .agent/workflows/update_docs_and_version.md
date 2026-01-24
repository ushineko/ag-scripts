---
description: Update documentation and version number for a sub-project
---

1.  **Identify Sub-Project**:
    -   Determine which sub-project tool the user is referring to (e.g., `select-audio-source`, `fake-screensaver`).
    -   Locate the main source file (e.g., `*.py`, `*.sh`) and the `README.md`.

2.  **Determine New Version**:
    -   Check the current version in the source file or README.
    -   Increment the version number (e.g., 1.0 -> 1.1, or 10.0 -> 11.0 if major changes).

3.  **Update Source Code**:
    -   Search for version strings using `grep` or `view_file` (look for `__version__`, `vX.Y`, or text in "About" dialogs).
    -   Update the version string to the new version.

4.  **Update README.md**:
    -   **Version**: Update any mentions of the version number (e.g., "Version 1.0").
    -   **Features**: Add bullet points for any newly implemented features under the "Features" or "Changelog" section.
    -   **Usage**: Update usage examples if CLI arguments or behavior changed.

5.  **Verify Consistency**:
    -   Ensure the version number in the Source Code matches the README.
    -   Ensure all new features discussed in the chat are documented.

6.  **Notify User**:
    -   Confirm that both code and docs are updated to the new version.
