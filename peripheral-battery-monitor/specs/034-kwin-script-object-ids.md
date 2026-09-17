# Spec 034: KWin recycles script *ids* too, and run() on a stale object is silent

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

Scene hotkeys stopped working again. Spec 029 stopped KWin serving a stale
script by *path*; the numeric id `loadScript` returns is a second handle with the
same defect. `install()` now identifies the object a load created by
introspection rather than by that id, destroys its predecessor with `stop()`
instead of `unloadScript`, and remembers the object across restarts. Reviewers
should look at `_script_objects()` and at why `unloadScript` was insufficient.

## Context

Reported as "the hotkeys didn't survive a reboot". They had in fact survived it —
KWin logged `aio-scenes: registering 18 shortcuts` at 09:55:20, seconds after
boot. What killed them was every *subsequent* `install()`, of which there were
four that morning from unrelated monitor restarts. The failure is cumulative, not
a boot event.

### What actually happens

- `unloadScript(path)` returns `true` and **does not destroy the Script object**.
  Its `/Scripting/ScriptN` node stays registered and its id stays occupied.
- `loadScript` returns an id that can collide with one of those survivors. In the
  reproduction it returned `2` while creating no object at all.
- `run()` on an already-run object is a **silent no-op** returning success.
- `isScriptLoaded(path)` still returns `true`, because the path did load.
- `stop()` is what actually destroys the object — confirmed by introspection,
  where `stop()` removed the node and `unloadScript` did not.

So `install()` reported success at every observable point while registering
nothing. This is spec 029's lesson repeating one level down: that spec made the
path unique and then verified with `isScriptLoaded`, which is exactly the check
it had itself documented as unreliable.

Proven by clearing the collision by hand: with all Script objects stopped, the
identical file loaded and registered immediately.

### Why a fresh process could not fix itself

`install()` only stopped an object it had created, and a newly started process
has none. The previous process's object therefore survived, holding its id, and
the ids drifted until one was recycled. That is why restarting the monitor never
helped and only clearing KWin's script objects did.

## Requirements

1. Identify the object a load created without trusting the returned id.
2. A load that creates no object must be reported as a failure.
3. Destroy the previous object rather than merely unloading its path.
4. A newly started process must be able to clean up its predecessor's object.
5. Do not disturb KWin scripts belonging to anything else.

## Acceptance Criteria

- [x] `_script_objects()` returns the `/Scripting/ScriptN` paths KWin holds, by
      introspection.
- [x] `install()` picks the object as the set difference across the load, and
      returns False logging `scene_shortcuts_no_new_object` when nothing appeared.
- [x] `install()` and `remove()` call `stop()` on the previous object before
      `unloadScript`.
- [x] The object path is persisted in `XDG_RUNTIME_DIR` and adopted by the next
      process, so a restart cleans up its predecessor.
- [x] Only objects this app created are ever stopped; foreign scripts are never
      enumerated for stopping.
- [x] A failed `Introspect` yields an empty set rather than looking like "no
      scripts loaded".
- [x] Verified live across four consecutive restarts: each logged
      `scene_shortcuts_installed` and KWin logged `registering 18 shortcuts`.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The persisted object path is only valid within a session.**
  `XDG_RUNTIME_DIR` and KWin both end at logout, so a value found there always
  refers to the running KWin. A mid-session KWin restart would invalidate it; on
  Wayland that ends the session anyway.
- **Stopping the predecessor's object is done blind.** The object exposes no
  properties — only `run()` and `stop()` — so there is no way to confirm it is
  ours beyond having recorded it ourselves.
- **The journal line remains the only true end-to-end proof.** `install()` now
  verifies far more than before, but "KWin actually grabbed the keys" is still
  observed rather than asserted.
- **Rollback**: revert the commit. Shortcuts work on the first install of a KWin
  session and silently stop at some later restart.

## Alternatives Considered

- Considered stopping the object at the id `loadScript` returned when a load
  creates nothing; rejected because spec 029 observed that id belonging to an
  unrelated script, so it could kill someone else's KWin script.
- Considered having the generated script call back over D-Bus to confirm
  registration; rejected for now because `install()` is synchronous at startup
  and waiting would mean spinning the Qt event loop. It remains the only way to
  make the check truly end-to-end, and is the natural next step if this recurs.

## Status: COMPLETE
