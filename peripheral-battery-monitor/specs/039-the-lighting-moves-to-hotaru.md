# Spec 039: the lighting moves to hotaru

**Issue**: [#13](https://github.com/ushineko/ag-scripts/issues/13)

## Executive Summary

Every write to the cooler and to every lit device leaves this program in one
commit: the RGB control, the LCD dashboard, the scenes and the eighteen numpad
shortcuts, along with `rgb_openrgb.py`, `aio_scenes.py`, `scene_service.py`,
`scene_shortcuts.py`, `aio_liquid.py`, `aio_dashboard.py`, `aio_color.py`,
`build_reels.py` and the `aio-scene` CLI. What stays is the poll, the rows, the
sparkline and the cooling alert. Reviewers should look at `aio_section.py`,
which goes from 1450 lines to 750, and at `TestNoWrites`, which is the guard
that used to permit RGB and no longer does.

## Context

[hotaru](https://github.com/ushineko/hotaru) is a Go rearchitecture of this
program's lighting and cooling half, and it has reached parity: it drives every
device OpenRGB can see, reads the Kraken directly over `/dev/hidraw` at about
two milliseconds against the hundred and five a liquidctl subprocess costs,
renders the dashboard on the 640x640 panel, keeps named scenes, and holds the
numpad shortcuts.

So the widget's write paths have nothing left to do, and leaving them in place
is not neutral. **Two processes writing one hidraw node is the failure this
area spent eighteen specs avoiding.** Specs 020, 021, 026, 033, 034, 036 and
037 are all, in one way or another, about one program keeping hold of something
it had already been asked to release.

### The line is writes

Reads continue. This program still polls the cooler, still shows coolant, CPU,
pump and fans, and still raises the cooling alert -- because an alert is owned
where it is visible, and this widget is the thing somebody actually looks at.
That was decided when the pump died silently and the CPU throttled to 0.20 GHz
behind a plausible-looking number.

Two readers of one device are fine and are what will exist until this program
is rewritten in Go and becomes a consumer of hotaru's API instead.

### What the hotkeys needed beyond deleting a file

The eighteen `AIOScene*` shortcut registrations live in KDE, not here. Removing
`scene_shortcuts.py` stops this program registering them again; it does not
remove the ones already recorded.

Two things were learned clearing them, both on the machine this runs on:

**KDE rewrites `kglobalshortcutsrc` from memory.** The entries were deleted
from the file, hotaru registered its eighteen shortcuts, and all eighteen of
these were back in the file a second later -- `kglobalaccel` keeps the table and
writes it out whenever anything registers. The supported route is
`org.kde.KGlobalAccel.unregister(component, action)`, which clears the daemon
and the file together and needs no logout.

**A stale entry does not necessarily block the new owner.** hotaru registered
its nine keys with all eighteen of these present and every key worked: the grab
belongs to the loaded KWin script, and KDE refuses a sequence only to a
*different* component. The stale entries were still worth clearing, and they
were not the obstacle they had been assumed to be.

## Requirements

**R1. Every write path goes, in one commit.** Not a staged retreat: a partial
removal leaves two programs writing one device, which is the specific thing
being prevented.

**R2. The reads and the alert stay.** The poll, the rows, the sparkline, the
degradation behaviour and the cooling notification are untouched.

**R3. The guard widens.** The test that forbade speed writes and explicitly
permitted RGB writes now forbids both, and asserts the removed modules are
absent.

**R4. Nothing registers a global shortcut.** The installer, the `.desktop`
entry and the startup path carry no shortcut registration, so the numpad stays
hotaru's across restarts.

**R4a. The settings those features wrote are removed from the file.** A
settings file listing a scene bank and an LCD interval describes a program that
no longer exists.

**R5. `openrgb-server` is not touched.** Its user unit is hotaru's dependency
now, and removing it would break the program that just took over.

## Acceptance Criteria

- [x] AC1. `rgb_openrgb.py`, `aio_scenes.py`, `scene_service.py`,
      `scene_shortcuts.py`, `aio_liquid.py`, `aio_dashboard.py`,
      `aio_color.py`, `build_reels.py` and `aio-scene` are gone, with their
      tests.
- [x] AC2. `aio_section.py` has no write path: no `post(`, no liquidctl write
      argv, no import of a removed module.
- [x] AC3. The AIO context menu offers only "Show AIO Section".
- [x] AC4. `peripheral-battery.py` registers no D-Bus scene service and no
      shortcuts, and reads no lighting, scene or LCD settings keys.
- [x] AC5. The poll, the rows, the sparkline, the degradation path and the
      cooling alert are unchanged, with their tests passing unmodified.
- [x] AC6. `TestNoWrites` forbids the RGB write path as well as the speed one,
      and asserts every removed module is absent.
- [x] AC7. The full suite passes: 266 tests, 36 subtests.
- [x] AC8. The README says what moved and where it went.
- [x] AC9a. The retired settings keys are dropped on load, the cleaned file is
      written at startup, and a file without them triggers no save.
- [x] AC9. Verified on the development machine: the widget runs, the AIO
      section still shows coolant, CPU, pump and fans, and hotaru's eighteen
      numpad keys still work with this program running.

## Risks & Assumptions

- **This is a deletion, and the code is the documentation.** Several of these
  modules encode hardware facts that cost days -- the RGBOverride ordering, the
  brightness-zero trap, KWin's five silent failures. They are not lost: hotaru
  carries the behaviour and its specs carry the reasoning, and the git history
  here keeps the originals.
- **The alert now depends on a poll this program no longer shares with
  anything.** That is a simplification rather than a risk: `aio_queue` stays
  and serialises the status reads against each other.
- **The version in the file had drifted ahead of the changelog.**
  `__version__` was 1.19.0 with no entries for 1.18.0 or 1.19.0. This release
  is 1.20.0 and the gap is recorded rather than reconstructed.
- **The retired settings keys are removed from the file**, dropped on load with
  the cleaned file written once at startup rather than whenever the user next
  happens to change something. A widget that is looked at rather than used may
  not save for weeks. The previous values remain in the `.bak` the atomic save
  already keeps, so a revert has something to read.
- **Rollback** is a revert: nothing else here is stateful and no migration
  runs.

## Alternatives Considered

Considered keeping the RGB menu as a fallback for a machine without hotaru;
rejected because a fallback that writes is exactly the second writer this
removal exists to prevent, and a machine without hotaru can install it.

Considered removing the cooling alert along with the rest of the AIO feature,
on the grounds that hotaru reads the same numbers; rejected because an alert
is owned where it is visible, and hotaru has no window.

## Status: COMPLETE
