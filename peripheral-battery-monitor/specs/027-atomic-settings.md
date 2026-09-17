# Spec 027: settings must survive a crash, and a corrupt file must not be silent

## Context

Reported: the bandwidth section "keeps losing its config" — configured with
`tailscale0` and `eno2`, reset several times, never sticks. Found on disk as
`"bandwidth_interfaces": []`.

The bandwidth section is not at fault. It persists on add, on remove, and
periodically, and a value written directly into the config survives a restart.
The fault is in how the whole settings file is written and read.

### The write truncates before it has anything to write

```python
with open(CONFIG_PATH, 'w') as f:
    json.dump(self.settings, f)
```

`open(path, 'w')` truncates the file to **zero bytes immediately**. The content
is then buffered and only reaches disk on close. Demonstrated:

```
before:                          {"bandwidth_interfaces": ["tailscale0", "eno2"], ...
after truncate, before flush:    ''
```

Any death in that window — crash, SIGKILL, power loss, a session ending mid-save
— leaves an empty or partial file. There is no temporary file and no backup, so
the previous good content is already gone.

### The read hides the damage and then overwrites it

```python
try:
    return {**default_settings, **json.load(f)}
except Exception:
    pass
return default_settings
```

A corrupt file is indistinguishable from no file. The app starts on defaults —
`bandwidth_interfaces: []` among them — reports nothing, and the next save writes
those defaults over whatever was left. The loss becomes permanent and silent.

This machine has had ample opportunity: hard resets from the defective CPU core
(documented in the sysadmin runbook), a thermal shutdown when the AIO pump failed,
and repeated service restarts.

It also explains why the loss looks selective. After a reset the user re-adds
whatever they notice missing — scenes, colours — so later inspection shows those
present and only the less-visible settings still empty.

### The actual cause: the test suite overwrites the real settings file

The two defects above are real and worth fixing, but they are not what lost the
config. `tests/test_battery_logic.py` constructs a real `PeripheralMonitor` with
`load_settings` mocked to return `{}` or `{"claude_section_enabled": True}` — and
leaves `save_settings` live while `CONFIG_PATH` still points at
`~/.config/peripheral-battery-monitor.json`. Any save during those tests writes
the mock's tiny dict over the user's real file.

Measured directly:

```
before running tests/test_battery_logic.py:  15 keys, bandwidth_interfaces=[tailscale0, eno2]
after:                                        2 keys, bandwidth_interfaces absent
```

The surviving keys were exactly `aio_scenes` and `claude_section_enabled` — the
latter being the literal value from the mock.

This explains every part of the report. The setting was not failing to save; it
was being destroyed afterwards, by a test run rather than by anything the user
did. It also explains why it resisted diagnosis: inspecting the bandwidth code
found nothing wrong, because nothing was, and the config kept reverting between
inspections because the suite was being run between them.

There is no `conftest.py`, so nothing isolated the path. Patching each call site
would leave the next test free to reintroduce it, so the redirect is done by
environment variable in a session-wide `conftest.py`.

## Requirements

1. The test suite must never touch the real settings file.
2. A crash during a save must never destroy the previous settings.
3. A corrupt or unreadable settings file must be reported, not silently replaced.
4. Recovery must be possible without the user reconstructing state by hand.

## Acceptance Criteria

- [x] `save_settings` writes to a temporary file in the same directory, flushes and
      fsyncs it, then atomically replaces the target, so the file on disk is always
      either the old complete content or the new complete content.
- [x] A save failure leaves the existing file untouched and is logged.
- [x] Before each successful replace, the previous good file is retained as a
      backup.
- [x] `load_settings` distinguishes: no file (first run, defaults, silent),
      readable file (use it), and unreadable/corrupt file (recover).
- [x] On a corrupt file, the backup is loaded if it parses, and the event is logged
      at warning with both paths named.
- [x] On a corrupt file with no usable backup, the corrupt file is preserved under a
      `.corrupt` suffix rather than being overwritten, and the event is logged.
- [x] Defaults are never silently substituted for a file that exists but failed to
      parse.
- [x] `CONFIG_PATH` honours a `PBM_CONFIG_PATH` override, and a session-wide
      `conftest.py` points it at a temporary file so no test can write the real one.
- [x] Running the full suite leaves the real settings file byte-identical.
- [x] Tests cover: normal round-trip, truncated file with a good backup, truncated
      file without a backup, absent file, and a failed save.
- [x] Existing tests still pass.

## Risks & Assumptions

- **`os.replace` is atomic only within one filesystem.** The temporary file is
  created in the same directory as the target, so this holds.
- **fsync costs a little on every save.** Settings are saved on user actions and on
  a slow periodic tick, not in any hot path, so the cost is irrelevant next to
  losing the file.
- **A backup can itself be stale** — it is the previous save, not a history. That is
  enough for the failure being fixed, where the live file is destroyed within
  milliseconds of being valid.
- **This does not recover the already-lost config.** The bandwidth interfaces were
  restored by hand as part of this work.
- **`tests/test_battery_logic.py` fails 25 of 70 when run alone** and passes inside
  the full suite, so those tests depend on another module having been imported
  first. Pre-existing — verified by stashing this work and reproducing it — and out
  of scope here, but it is a latent trap for anyone running one file.
- **Rollback**: revert the commit; saving returns to the truncating write.

## Alternatives Considered

- Considered writing settings less often to narrow the window; rejected as reducing
  the probability of an unbounded failure rather than removing it.
- Considered a lock file around the save; rejected because the problem is not
  concurrency — a single process crashing mid-write is enough, and the instance lock
  already exists.
- Considered JSON schema validation on load; rejected as out of scope. The failure
  here is an empty or truncated file, which `json.load` already rejects.

## Status: COMPLETE
