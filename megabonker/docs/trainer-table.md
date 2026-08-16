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

| Entry | Type | Purpose |
| :--- | :--- | :--- |
| Infinite Health | Auto Assembler script | hooks both health write sites; blocks decreases, records the player object address |
| Health | 4 Bytes, pointer `pPlayer` + `0x10` | live health, re-resolves every run |

Enable the script first — the `Health` entry reads through a symbol the script
creates, so it is inert until the script is active and the game has written
health at least once.

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
