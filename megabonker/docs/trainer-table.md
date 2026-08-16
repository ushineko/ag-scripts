# Megabonk Cheat Engine table

`tables/Megabonk.CT` — health pointer plus godmode, built against the Feb-2026
Windows build running under Proton.

Complementary to save editing: megabonker handles persistent state between runs,
this handles live values during one.

## Contents

- [What the table contains](#what-the-table-contains)
- [Loading it](#loading-it)
- [How it works](#how-it-works)
- [Re-deriving after a game update](#re-deriving-after-a-game-update)
- [Gotchas that cost time](#gotchas-that-cost-time)

## What the table contains

```
Megabonk Trainer  -- ENABLE THIS FIRST, then jump once
├── Godmode (block damage)
├── Health                       pPlayer + 0x10
├── Stats                        27 entries, pStats2 + 0x1C + id*0x10
└── debug                        pPlayer / pStats2 raw pointers
```

The **activation** script installs all three hooks and publishes two symbols. It
makes no gameplay change on its own — godmode is a separate child entry gated on
a `gGodmode` flag byte, so stats can be edited without invincibility and vice
versa.

Order matters: enable activation, then **jump once**. `pStats2` is only populated
when the stat getter runs with Jump Height's id, so every Stats entry reads `??`
until you jump. `Health` works as soon as the game writes health.

## Loading it

Cheat Engine runs inside the Proton prefix, so its file dialogs see Windows
paths. Its table directory is:

```
<prefix>/drive_c/users/steamuser/Favorites/
```

Copy the table in, then `File → Open` in Cheat Engine:

```bash
cp tables/Megabonk.CT \
   /mnt/Data3/SteamLibrary/steamapps/compatdata/3405340/pfx/drive_c/users/steamuser/Favorites/
```

Saving from Cheat Engine writes back to that prefix path, **not** to this repo —
copy it back and commit when the table changes.

## How it works

Health is a 4-byte int at **offset `0x10`** inside the player object. The object
is GC-allocated per run, so its address changes every run — which is why a plain
address entry is useless and a pointer is required.

Two code sites write it:

| Site | Address | Instruction | Role |
| :--- | :--- | :--- | :--- |
| `healthSet` | `GameAssembly.dll+428D28` | `mov [rbx+10],edi` | clamped setter (heals, init) |
| `healthDmg` | `GameAssembly.dll+428419` | `mov [rdi+10],eax` | damage application |

`healthSet` is preceded by a float clamp between 0 and max, then
`cvttss2si edi,xmm0`. `healthDmg` is followed by `cmp [rdi+10],0` / `jg`, i.e.
the death check — that is what identifies it as the damage path. **Hooking only
`healthSet` does not stop damage**; both are needed.

Each hook does two things:

1. `mov [pPlayer],rbx` (or `rdi`) — records the object's address. This is the
   pointer the `Health` entry reads through. Because it refreshes on every
   health write, it self-corrects if the GC relocates the object, which is why
   this beats a pointer scan on an IL2CPP title.
2. `cmp` + `jl` — skips the write when the incoming value is lower than current.
   Damage is ignored; heals and max-HP increases still apply.

In `healthDmg` the stolen `cmp dword ptr [rdi+10],00` is replayed **last**,
immediately before returning, because the game's following `jg` depends on its
flags. Skipping the write leaves health above zero, so the death branch is not
taken.

Enemies are unaffected — verified in game. `healthDmg` is the player's damage
path, not a shared entity setter, so no class-pointer guard is needed.

## Stats array (work in progress)

Every stat on the in-game Stats screen lives in one flat array of 16-byte
entries, indexed by a stat ID:

```
address = arrayBase + (id * 0x10)
  +0x00  float   the value
  +0x04  int     the stat id
  +0x0C  int     the stat id again
```

Percentages are stored as **fractions** - crit chance `0.01` displays as 1%,
evasion `0.0783` as 8%. Multipliers are stored as shown (`1.0` = 1.0x).

### Stat IDs

Verified by writing a unique value into each id and reading the Stats screen.

| id | Stat | id | Stat |
| ---: | :--- | ---: | :--- |
| 1 | Max HP | 25 | Knockback |
| 2 | HP Regen | 26 | Movement Speed |
| 3 | Shield | 27 | Jump Height |
| 5 | Armor | 30 | Pickup Range |
| 6 | Evasion | 31 | Luck |
| 10 | Size | 32 | Gold Gain |
| 11 | Duration | 39 | Difficulty |
| 12 | Projectile Speed | 40 | Crit Damage |
| 13 | Damage | 41 | Powerup Multiplier |
| 16 | Attack Speed | 42 | Powerup Drop Chance |
| 17 | Projectile Count | 46 | Projectile Bounces |
| 18 | Lifesteal | 47 | Extra Jumps |
| 19 | Crit Chance | 48 | Overheal |
| 24 | Damage to Elites | | |

Offset = `0x1C + id * 0x10`.

Not resolved: **XP Gain**, **Elite Spawn Increase** and **Thorns**. A second
probe was inconclusive because a recalculation rebuilt the computed array before
the screen could be read. Finishing the map means probing the **source** array
instead, where values persist - best done on a throwaway run, since a bad write
to the source is more consequential than to the computed copy.

**Silver Gain** is not in the run array at all - it comes from the permanent shop
upgrade stored in `progression.json`.

The array order does **not** follow the Stats screen. Ids 1-6 happen to line up,
then diverge - Damage is id 13, not 9, and Shield is 3, not 4. Guessing from
screen position produces entries that silently do nothing, which is exactly what
happened before this was measured.

### Two arrays: source and computed

There are two stat arrays in memory, and the relationship matters:

| | Role |
| :--- | :--- |
| **source** | the game's real values, built from your items and upgrades |
| **computed** | what the Stats screen displays and what `pStats2` points at |

**The computed array is rebuilt from the source array on every recalculation** -
triggered by picking up an upgrade, levelling, and periodically. Anything written
into the computed array is therefore *transient*: it applies immediately and
survives until the next recalculation, then reverts.

Practical rule: **freeze stat entries, do not just set them.** Ticking an entry's
Active box makes Cheat Engine rewrite it many times a second, which wins against
the recalculation. A one-off write will appear to work and then silently revert -
first observed when an agility tome reset an edited movement speed.

The two arrays are otherwise near-identical; evasion differs because the computed
copy holds the post-diminishing-returns value.

This also breaks naive probing: writing unique values into the computed array to
identify stats works only if you read the screen before the next recalculation.
A probe that fails this way looks like the stats were never written at all.

### Capturing the base

Solved by hooking the generic stat **getter** and filtering on which stat is
being read.

```
GameAssembly.dll+DD28C9   movss xmm0,[rcx+rax*8+2C]

arrayBase = rcx + 0x1C
rax       = 2 * (id - 1)      the instruction before it is `add rax,rax`
```

Only the player reads Jump Height (id 27, so `rax = 0x34`), so filtering on that
guarantees the capture is the player's array and never an enemy's. Enemies do
get stats arrays through the same code, which is why the *writer* at
`GameAssembly.dll+DCFBE1` is unusable for this - it latches onto whichever
entity spawned last.

Table entries are then `pStats2` + `0x1C + id*0x10`:

| Stat | Offset | Stat | Offset |
| :--- | ---: | :--- | ---: |
| Max HP | `2C` | Damage | `AC` |
| HP Regen | `3C` | Crit Chance | `14C` |
| Overheal | `4C` | Movement Speed | `1BC` |
| Shield | `5C` | Jump Height | `1CC` |
| Armor | `6C` | Pickup Range | `1FC` |
| Evasion | `7C` | | |
| Lifesteal | `8C` | | |
| Thorns | `9C` | | |

Enable the script, then **jump once** to prime `pStats2` - the entries read `??`
until the getter has been called with id 27.

### The two identical getters - do not wildcard this AOB

The module contains **two byte-identical copies** of that getter. They differ
only in the `rel32` displacements of the two `call` instructions ~60 bytes
earlier. Your code only ever runs one of them.

A short AOB matches both, and Cheat Engine hooks the first - a function the
player never calls, so the hook installs cleanly, reports success, and does
nothing. This cost several hours to find.

The AOB therefore starts 0x40 bytes before the injection point (to include the
differing call displacements) and injects at `statAob+40`. **The displacements
must be literal.** Wildcarding them - the usual practice for making a pattern
survive updates - removes the only bytes that distinguish the two copies and
reintroduces the bug.

Consequence: this AOB will break on a game update and must be re-derived. That
is the correct trade; a pattern that cannot tell the two functions apart is
worse than one that needs maintenance.

**Verify which copy got hooked** rather than trusting that it enabled:

```bash
pid=$(pgrep -x Megabonk.exe | head -1)
base=$(grep -m1 GameAssembly.dll /proc/$pid/maps | cut -d- -f1)
python3 -c "
mem=open('/proc/$pid/mem','rb')
for name,rva in (('right',0xDD28C9),('wrong',0xDAC239)):
    mem.seek(0x$base+rva); d=mem.read(6)
    print(name, d.hex(' '), 'HOOKED' if d[0]==0xE9 else '')"
```

Note the trap this creates for uniqueness checks: once Cheat Engine has patched
one copy, that copy no longer matches the pattern, so a scan run afterwards
reports the AOB as unique when it is not. Compare the two copies using bytes
that are unpatched in both.

## Open items

### Unmapped stats: XP Gain, Elite Spawn Increase, Thorns

Three stats on the Stats screen have no confirmed id.

**Thorns is probably id 4.** Immediately before the second probe, id 4 held
`999` and the screen showed Thorns `999` - the only stat with that value. It was
not confirmed because the probe write did not survive to be read.

**XP Gain and Elite Spawn Increase** showed `10.0x` and `40.0x` during the first
probe, colliding with Size (id 10) and Crit Damage (id 40). Either they are
derived from those stats, or they read from somewhere outside this array.

### How to finish it

Probe the **source** array, not the computed one. The second probe failed
because a recalculation rebuilt the computed array before the screen could be
read; values written to the source survive that.

Procedure:

1. Locate both arrays by scanning for the id pattern (`value` float at +0, id
   repeated at +4 and +C, stride `0x10`, 50 entries). The source array is the one
   holding plausible game values; the computed one is where `pStats2` points and
   where your edits land.
2. Back up the source array first - a bad write there is more consequential than
   to the computed copy, because everything is rebuilt from it.
3. Write a distinctive value (e.g. `100 + id`) into ids 4, 7, 8, 9, 14, 15, 20-23,
   28, 29, 33-38, 43-45, 49.
4. Read the Stats screen, restore the backup.

Do this on a throwaway run rather than one you care about. Writing many stats at
once also triggers audible in-game feedback as thresholds fire - probe in small
batches.

## Re-deriving after a game update

A patch will eventually move these offsets. The AOB patterns survive small
shifts; if they stop matching, redo the discovery:

1. Find the current health value by scanning (start with your visible HP)
2. Right-click the address → **Find out what writes to this address**
3. Take a hit. Two instructions appear
4. The one followed by `cmp [reg+10],0` / `jg` is the damage path
5. `Ctrl+Alt+A` → Template → AOB Injection on each, then re-apply the two
   additions above

To confirm a hook is actually installed, read the process memory rather than
trusting the UI — `E9` as the first byte means the jump is in:

```bash
pid=$(pgrep -x Megabonk.exe | head -1)
base=$(grep -i GameAssembly.dll /proc/$pid/maps | head -1 | cut -d- -f1)
python3 -c "
import sys
pid, base = '$pid', int('$base', 16)
with open(f'/proc/{pid}/mem','rb') as m:
    m.seek(base + 0x428D28); print(m.read(10).hex(' '))"
```

## Gotchas that cost time

**Never press Execute in the Auto Assemble window.** It injects immediately and
untracked, which overwrites the very bytes `aobscanmodule` searches for. The
table checkbox then fails silently and springs back. Recovery is quitting the
game entirely — a new run is not enough, because the patched bytes live in the
loaded module for the life of the process. Use `File → Assign to current cheat
table` and drive it with the checkbox.

**Close "Find out what writes" windows before enabling scripts.** They leave
debug breakpoints installed, which can also stop the AOB matching.

**A new run is not a new process.** New run = new player object = new address
(the problem the pointer solves). New process = module reloaded = clean code
bytes (what a botched injection needs).
