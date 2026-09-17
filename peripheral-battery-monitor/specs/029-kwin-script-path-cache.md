# Spec 029: KWin caches scripts by path, so a stable path cannot be reloaded

## Context

Reported after a reboot: the scene hotkeys stopped working, from the keys and
from the context menu. They had worked before that reboot.

Every layer reported health. `install()` returned True. `isScriptLoaded` returned
true. The D-Bus service was registered, `Apply(1)` returned true over D-Bus, and
the scenes reached the hardware when invoked directly. Probe scripts registered
shortcuts that fired. Nothing named a fault.

## The fault

`_script_path()` returned a fixed path, on this reasoning:

```python
"""Stable path so a reload replaces the previous script rather than stacking."""
```

**KWin caches loaded scripts by path.** `loadScript` on a path it has already
seen returns the existing script's id *without re-reading the file*, and `run` on
an already-run script does nothing. So every reload after the first in a given
KWin session is a silent no-op that reports success at every observable level:
`install()` returns True, `isScriptLoaded` returns true, and the file on disk is
genuinely the new one — while the shortcuts actually registered in KWin are
whatever the first load of that session installed.

Demonstrated directly. Loading the canonical path returned the id of an unrelated
script (`slack-focus-monitor`, which had been loaded first and held id 1) and
produced no output. Copying the identical file to a fresh path and loading that
returned a new id and immediately logged `registering 18 shortcuts`.

Within one session the bug is invisible, because the first load works. It bites
across a restart: the first load of a new session is the one that must succeed,
and if it does not, every later attempt is a cached no-op. The shortcuts then
cannot be recovered by restarting the monitor — only by restarting KWin. That is
why it looked like a hard break rather than a flaky one, and why restarting the
monitor repeatedly never helped.

### Why the evidence was misleading

Worth recording, because the wrong conclusions were all well-supported:

- `install()` reported success it never verified.
- `isScriptLoaded` reported true for a script that was not running.
- Diagnostic probe scripts *worked* — because they used different paths, so they
  loaded properly. This made the key grabs look healthy.
- `AIOScene1` fired during probing, because the probe performed the registration
  the real script had never got to perform.
- The monitor's own logs go to a file, not the journal, so an early "there are no
  log lines" reading was simply looking in the wrong place.

None of the shortcut machinery was broken. Only the loading of it.

## Requirements

1. Loading the generated script must actually read the generated file, every time.
2. A load that did not take must be reported as a failure, not assumed to succeed.
3. Scripts and their files must not accumulate across reloads.
4. The shortcut path must be observable from the KWin side.

## Acceptance Criteria

- [x] `_script_path()` returns a unique path per install, so KWin's by-path cache
      cannot serve a stale script.
- [x] `install()` unloads the previously installed script by its own path, and
      removes stale generated files from earlier runs.
- [x] `install()` verifies with `isScriptLoaded` and returns False when the load
      did not take, logging the unverified reply.
- [x] `remove()` deletes the generated file as well as unloading it.
- [x] The generated script logs its registration count on run, and logs each
      shortcut activation, so the KWin half of the chain is visible in the journal.
- [x] Restarting the monitor produces a fresh, running script and working
      shortcuts without restarting KWin.
- [x] Existing tests still pass.

## Risks & Assumptions

- **Unique paths leave files behind if the process dies.** They live in
  `XDG_RUNTIME_DIR`, which is cleared on logout, and `install()` sweeps siblings
  matching the generated prefix on every run.
- **Unload-then-load is not atomic.** There is a brief window with no shortcuts
  registered. It is milliseconds, on a path that only runs at monitor start.
- **The registration logging is deliberately chatty** — one line per keypress. It
  is what turns "the hotkey did nothing" from an unanswerable report into a
  one-line check, which this investigation badly needed.
- **Rollback**: revert the commit. Shortcuts work until the first failed load of a
  KWin session, then cannot be recovered without restarting KWin.

## Alternatives Considered

- Considered unloading by plugin name rather than path; rejected because KWin
  returned false for the name form, and the path form does unload correctly — the
  problem was never the unload, it was `loadScript` serving a cached id.
- Considered restarting KWin when a load fails; rejected as wildly
  disproportionate, and it would drop every other KWin script and window rule.
- Considered abandoning KWin scripting for `.desktop` shortcuts; rejected because
  spec 025 established those only take effect at the next login, which is worse.

## Status: COMPLETE
