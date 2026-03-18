# Refactor: Split Monolithic File into Modules

> **Ticket**: No associated ticket — personal project.

## Context

`audio_source_switcher.py` is ~2500 lines in a single file. The code already has clean class boundaries, making extraction into separate modules straightforward. There are also a few code quality issues (dead code, duplication) to address alongside the split.

## Requirements

### Module Split

Extract the existing classes into a package structure:

```
audio-source-switcher/
├── audio_source_switcher/        # New package
│   ├── __init__.py
│   ├── controllers/
│   │   ├── __init__.py
│   │   ├── audio.py              # AudioController
│   │   ├── bluetooth.py          # BluetoothController, ConnectThread
│   │   ├── pipewire.py           # PipeWireController, VolumeMonitorThread
│   │   └── headset.py            # HeadsetController
│   ├── config.py                 # ConfigManager
│   ├── gui/
│   │   ├── __init__.py
│   │   └── main_window.py        # MainWindow
│   └── cli.py                    # handle_volume_command, main, arg parsing
├── audio_source_switcher.py      # Thin entry point (imports and calls main)
├── tests/
├── install.sh
├── uninstall.sh
└── README.md
```

- Preserve the top-level `audio_source_switcher.py` as a thin entry point so existing installs, hotkeys, and CLI invocations continue to work unchanged.
- Each module should import only what it needs — no circular dependencies.
- No behavioral changes. This is a pure structural refactor.

### Code Quality Fixes

1. **Remove dead code**: `PipeWireController.get_sink_volume` and `set_sink_volume` are defined twice (~lines 738-801). Remove the duplicate definitions.
2. **Extract volume sync logic**: The volume synchronization logic appears twice in `MainWindow` with minor differences. Extract into a single method.
3. **Fix potential bug**: An `except Exception` block references `jdsp_outs` which may be unbound if the preceding `try` block failed before that assignment. Add a guard or restructure.

## Acceptance Criteria

- [x] All classes extracted into separate modules per the structure above
- [x] Top-level `audio_source_switcher.py` works as a thin entry point
- [x] All existing CLI invocations work unchanged (`--connect`, `--vol-up`, `--vol-down`)
- [x] Single-instance detection (QLocalSocket) still works
- [x] Duplicate `get_sink_volume`/`set_sink_volume` removed
- [x] Volume sync logic consolidated into one method
- [x] `jdsp_outs` unbound variable guarded
- [x] All existing tests pass
- [x] No behavioral changes — pure structural refactor

## Technical Notes

- The existing class boundaries are clean; most extractions are cut-and-paste with import adjustments.
- `MainWindow` is the largest class (~1560 lines). Further decomposition of the GUI (e.g., extracting dialog methods or tray logic) is out of scope for this spec but could be a follow-up.
- `install.sh` and `uninstall.sh` do not reference the Python file path — no changes needed.

## Status: COMPLETE
