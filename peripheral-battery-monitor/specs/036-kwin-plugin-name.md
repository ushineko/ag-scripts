# Spec 036: KWin's script handle is a plugin NAME, not a file path

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

Third recurrence of "scene hotkeys stop working". Specs 029 and 034 both treated
the script's file path as its handle, because `isScriptLoaded(path)` returns
true. It is not a handle: `loadScript` has a two-argument form taking an explicit
`pluginName`, and the one-argument form merely defaults that name to the path.
Loading under a stable name allocates a fresh Script object; the path-only form
returned ids belonging to other scripts. Reviewers should look at `PLUGIN_NAME`
and at why unloading by path leaked objects.

## Context

Spec 029 made the script path unique, to defeat KWin's by-path cache. Spec 034
stopped trusting the returned id and began identifying the new Script object by
introspection. Both helped, and neither held: the hotkeys broke again after a
handful of monitor restarts.

### The actual API

```
loadScript(in s filePath, in s pluginName, out i) 
loadScript(in s filePath, out i)
unloadScript(in s pluginName, out b)
isScriptLoaded(in s pluginName, out b)
```

`unloadScript` and `isScriptLoaded` take a **plugin name**. The one-argument
`loadScript` defaults that name to the file path, which is why passing paths
appeared to work and why two specs concluded the path was the handle.

### Why spec 034's fix could not hold

`install()` stopped the object it had tracked, but still called
`unloadScript(stale_path)` on leftovers. **Unloading removes KWin's list entry
without destroying the object.** The list shrinks while the objects do not, and
the id `loadScript` returns tracks the list size — so it lands on a slot still
occupied by a live object. That load creates nothing, and `run()` on the
already-running object it collides with is a silent no-op. The previous fix was
creating the very collision it detected.

Demonstrated directly: with the path-only form the load returned `2` and created
no object; with `loadScript(path, "aio-scenes")` it returned `3` and created
`Script3`, which ran and registered 18 shortcuts immediately.

### Why the obvious shortcut was wrong

Stopping whatever object sits at the returned id would "fix" the collision. This
machine has `slack-focus-monitor` enabled, and spec 029 recorded `loadScript`
returning *its* id — so that shortcut would silently kill an unrelated script.

## Requirements

1. Load, unload and check the script by a stable plugin name.
2. A load that creates no Script object must still be reported as a failure.
3. Never stop or unload anything this app did not create.
4. Repeated installs must not accumulate Script objects.

## Acceptance Criteria

- [x] `PLUGIN_NAME` is a module constant and the script is loaded with the
      two-argument `loadScript(path, PLUGIN_NAME)`.
- [x] `unloadScript` and `isScriptLoaded` are called with `PLUGIN_NAME`, never
      with a path.
- [x] `install()` no longer calls `unloadScript` on stale paths; stale files are
      deleted, not unloaded.
- [x] The new object is still identified by set difference, and a load creating
      no object still logs `scene_shortcuts_no_new_object` and returns False.
- [x] `remove()` stops the object and unloads by name.
- [x] Verified live across six consecutive restarts: each logged
      `scene_shortcuts_installed name=aio-scenes id=3` and KWin logged
      `registering 18 shortcuts`, with the Script object count steady at two
      (ours plus `slack-focus-monitor`) rather than growing.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The unique per-install path is now redundant** but retained: it costs
  nothing, and it still guarantees KWin cannot serve stale *content* from its
  by-path cache, which was spec 029's real finding.
- **The object-difference check is now belt-and-braces.** The returned id is
  correct in practice under a named load; the check stays because a load
  creating no object is the failure that hid across two specs.
- **Rollback**: revert the commit. Shortcuts work until enough restarts
  accumulate a colliding id, then stop silently.

## Alternatives Considered

- Considered stopping the object at the returned id on collision; rejected
  because that id has been observed belonging to `slack-focus-monitor`.
- Considered keeping the path as the name and only fixing the unload; rejected
  because the two-argument form removes the ambiguity entirely rather than
  working around it.

## Status: COMPLETE
