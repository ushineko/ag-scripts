---
description: Iteratively run, capture logs, and debug a program until a success condition is met.
---

1.  **Preparation**:
    *   **Identify Goal**: What is the **Success Condition**? (e.g., "Battery level 70% shows in logs", "Error X is gone").
    *   **Ensure Observability**:
        *   Does the program output logs to stdout/stderr?
        *   Does it support a `--debug` flag? Use it.
        *   **CRITICAL**: If the program is NOT amenable to log capturing (silent, no debug mode), you **MUST** modify the code first to add print/logging statements. Do not skip this.

2.  **Clean Slate**:
    *   **Kill Existing Instances**: Before every run, ensure to kill any background instances or GUI processes of the target tool (e.g., `pkill -f my_script.py`) to ensure you are capturing the *new* run and not an old one.

3.  **Execution Loop**:
    *   **Run**: Execute the program.
        *   If it's interactive or long-running, use `timeout` or run in background with redirection: `python3 script.py --debug > debug.log 2>&1`.
    *   **Capture**: Read the output (stdout or log file).
    *   **Analyze**:
        *   Did the **Success Condition** occur?
        *   Are there new errors?
    *   **Decision**:
        *   **Success**: If yes, STOP. You are DONE. 
            *   Be sure to remove all temporary logs and files created by this process so you don't clutter up the project.
        *   **Failure**:
            *   Analyze the logs to understand *why*.
            *   **Adjust**: Apply a fix to the code OR add *more* specific logging if the root cause is still hidden.
            *   **Loop**: Go back to **Clean Slate** and repeat.