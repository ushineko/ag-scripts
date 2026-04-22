# Research: VSCode IPC protocol as a cross-platform window-detection backend

**Question:** can we ditch KWin scripting (KDE-only) and talk to VSCode's
internal IPC socket directly from Python, to enumerate open windows and
their workspaces on any platform?

**Answer:** yes. It works. A ~280-line Python POC ([vscode_ipc_probe.py](vscode_ipc_probe.py))
connects to the VSCode main Unix socket, performs the client handshake,
invokes `diagnostics.getMainDiagnostics()`, and parses the reply. Round-trip
time is **~2–3 ms** on the author's setup.

## Measurements

| Approach | Latency | Per-window PID | Workspace paths | Platform dep |
| -------- | ------- | -------------- | --------------- | ------------ |
| `code --status` CLI | **~2400 ms** | yes (text-parsed) | no (only caption label) | VSCode only |
| KWin scripting (v1.x) | ~500 ms | **no** (main-VSCode only) | no (only caption label) | **KDE Plasma 6** |
| IPC probe (this POC) | **~2.9 ms** | **yes** (renderer PID) | **yes** (real `folderURIs`) | VSCode only |

The IPC approach dominates on every axis that matters:

- **800× faster** than `code --status` (which spawns Electron each call)
- **~170× faster** than the KWin path (which load-runs-unloads a KWin script
  and reads journalctl)
- Returns **actual folder URIs** from each window — so we match VSCode's
  recent list by path directly, with zero caption-parsing heuristics. That
  eliminates the entire class of "caption label prefix-matching" false
  positives (`aiq-ralph` vs `aiq-ralphbox`) we already had to work around.
- Gets the **real per-window renderer PID**, which /proc can turn into an
  accurate per-window launch time without any of the "in-memory tracking
  only, because Electron gives KWin the main PID" workaround in v1.8.

## What the response contains

Live sample from the POC on the author's machine (2 running windows — one
folder workspace, one multi-root `.code-workspace`):

```
socket: /run/user/1000/vscode-f56deafd-1.11-main.sock
RPC round-trip: 2.9 ms
mainPID: 2372499
windows: 2
  id=2 pid=2492977 title='Spec vscode-launcher too… - ag-scripts - Visual Studio Code'
      folders=['/home/nverenin/git/ag-scripts']
  id=1 pid=2372593 title='EMM endpoints for CVE-re… - platform-backend (Workspace) - Visual Studio Code'
      folders=['/home/nverenin/git/platform-backend', '/home/nverenin/git/platform-ui',
               '/home/nverenin/git/aiq_agent_go', '/home/nverenin/git/aiq_agent_python',
               '/home/nverenin/git/attackiq_ai', '/home/nverenin/git/platform-infrastructure']
```

Every `folderURIs` entry in the multi-root case corresponds precisely to the
`folders[]` array inside the `.code-workspace` file. No parsing needed.

## Protocol summary

Full details in the docstring at the top of the POC. Brief:

### Framing (13-byte header)

```
 offset  size  field
 0       1     ProtocolMessageType   (uint8; 1 = Regular, used for everything we need)
 1       4     id                     (uint32 BE — unused for simple probe)
 5       4     ack                    (uint32 BE — unused for simple probe)
 9       4     body length            (uint32 BE)
 13      N     body                   (VSBuffer-serialized data)
```

Reference: `src/vs/base/parts/ipc/common/ipc.net.ts` — `ProtocolMessageType`
enum and `ProtocolReader`.

### VSBuffer serialization (tagged TLV)

```
 tag byte       meaning
 0              undefined
 1              string   — VQL length + UTF-8 bytes
 2, 3           buffer   — VQL length + raw bytes
 4              array    — VQL length + N recursively serialized elements
 5              object   — VQL length + JSON-encoded bytes
 6              int      — VQL-encoded non-negative int
```

VQL = standard 7-bit-per-byte varint, high bit = "more bytes follow". Zero
is `0x00`.

Reference: `src/vs/base/parts/ipc/common/ipc.ts` — `DataType`, `serialize`,
`deserialize`.

### Client handshake

The entire handshake is one line (`IPCClient` constructor):

```ts
protocol.send(serialize(ctx));
```

The client sends ONE Regular-framed message whose body is a serialized
string identifying itself ("main" in VSCode's own usage; we pass
`"vscl-probe"` — the server doesn't validate the ID).

The server also sends `serialize([200])` (ResponseType.Initialize) around
the same time. Our POC just reads and discards that frame when it arrives.

Reference: `src/vs/base/parts/ipc/common/ipc.ts` lines 985–997 (`IPCClient`
constructor).

### RPC call

Client sends ONE Regular-framed message:

```
body = serialize([100 /* RequestType.Promise */, request_id, channel_name, method_name])
     + serialize(arg)  // undefined if none
```

Server responds with ONE Regular-framed message:

```
body = serialize([201 /* PromiseSuccess */, request_id])
     + serialize(return_value)
```

(Error responses use types 202 or 203. The POC handles both.)

Reference: `src/vs/base/parts/ipc/common/ipc.ts` — `ChannelClient.sendRequest`
and `ChannelServer.onRequest`.

### The `diagnostics` channel

Registered in `src/vs/code/electron-main/app.ts`:

```ts
this.mainProcessNodeIpcServer.registerChannel('diagnostics', diagnosticsChannel);
```

Implements `IDiagnosticsMainService`:

- `getMainDiagnostics()` — returns per-window info, main PID, GPU state, etc.
- `getRemoteDiagnostics(opts)` — only relevant for Remote-SSH / WSL setups

We only need `getMainDiagnostics`. Defined in
`src/vs/platform/diagnostics/electron-main/diagnosticsMainService.ts`.

## What else the IPC exposes

The diagnostics channel isn't the only one. The `launch` channel — used by
`code --new-window <path>` under the hood — lets us:

- `start({args, userEnv})` — open a new window / folder / file in the
  running instance. This is how `code --new-window foo` actually works;
  it sends this call to the already-running process.
- `getMainProcessId()` — returns main PID.

A Python client could issue `launch.start({args: ["--new-window", "/path"]})`
to open a new window without spawning a second VSCode binary. That would cut
launch latency too, but it's speculative optimization — not needed for the
running-state-detection use case.

The full channel roster (from `app.ts` `registerChannel` calls): `launch`,
`diagnostics`, `auth`, `window`, `settings-sync`, `shared-process`, etc.
Most are internal and not useful to us.

## Limitations / risks

### Protocol stability

This is an **internal** VSCode API, not a documented public one. Things
that could change between VSCode versions:

- **`DataType` enum values**: these are a wire format, and the enum is
  declared `const enum` in TypeScript — inlined at compile time. Changing
  the numbering would break all existing clients, so stability is implicit.
  Unchanged since the IPC refactor years ago.
- **Channel names** (`diagnostics`, `launch`, etc.): named strings, could
  theoretically be renamed, but these are load-bearing for `code --status`
  itself.
- **`getMainDiagnostics()` return shape**: could gain fields (additive,
  safe) or have fields renamed (breaking). Our parser ignores extras.
- **`folderURIs` structure**: currently `{scheme, authority, path, query, fragment}`
  — standard VSCode `URI` shape, also stable for years.

In practice the risk is **graceful-degradation**: if a future VSCode version
breaks the protocol, our parser throws or returns empty. That's no worse
than the current KWin path, which would also fail if KWin's JS API shifted.

### Handshake quirks

The POC's reader skips the server's `Initialize` message (type 200) before
accepting a response. If VSCode ever interleaves other protocol messages
(ack, keepalive) between the handshake and our reply, the POC's dumb
reader-loop handles them by just skipping non-Regular frames. A production
client should also send keepalive acks for long-lived connections — we
don't need that for one-shot scans.

### Socket discovery

Current logic: `glob XDG_RUNTIME_DIR for vscode-*-main.sock, pick most-recent`.
This is correct on Linux. On macOS the sockets live at
`$TMPDIR/vscode-ipc-*.sock`. On Windows they're **named pipes**:
`\\.\pipe\vscode-ipc-*-sock`. Non-trivial to speak named-pipe protocol
from Python (needs `pywin32`), but conceptually the same framing.

### Not a replacement for actions

This POC only reads state. Activate / Stop are separate problems:

- **Activate**: the `launch.start()` RPC can focus an existing window by
  passing a path that matches an open workspace. That's the documented
  `code --reuse-window <path>` behavior.
- **Stop**: needs investigation. There might be a `window.closeWindow`
  RPC, or we might need `kill <renderer_pid>` which is ugly. Research
  TBD.

## Recommendation

### If we do a cross-platform rewrite

Use this approach. It's strictly better on every axis than both the
current KWin-based implementation AND the `code --status` fallback I
originally proposed in [spec 010](../specs/010-cross-platform-detection-proposal.md).

Proposed architecture, replacing what was in spec 010:

- **`VSCodeIPCInspector`** — speaks the protocol (harden this POC into a
  proper class, ~400 lines including socket discovery per-platform and
  connection reuse). Primary backend on every platform.
- **No fallback needed** on the read path — if the IPC isn't available
  (no socket), VSCode isn't running. Just return "nothing open".
- **`launch.start()`** RPC for launching. Avoids the 2.4 s Electron CLI
  startup when we want to open a workspace.

This makes the tool portable to GNOME, Hyprland, Sway, macOS, and
eventually Windows (named-pipe bridge needed). KWin dependency is gone.

### If we stay with v1.8

Still a meaningful upgrade opportunity: **replace the KWin scanner with
this approach on KDE too**. It's ~170× faster, cleaner (no `journalctl`
race, no nonce workaround, no KWin script file churn), and more accurate
(per-window PID, real folder URIs). No user-visible behavior change
required — just a better engine under the existing UI.

For a conservative staged rollout:

1. **Phase 1 (low-risk)**: add `VSCodeIPCInspector` as a new backend
   with feature-flag opt-in. Keep KWin as default. Collect reliability
   feedback via debug logs.
2. **Phase 2**: flip the default to IPC, KWin becomes the fallback when
   the socket isn't found (shouldn't happen in practice — VSCode always
   creates it).
3. **Phase 3**: remove the KWin path. Module becomes `~200 lines` smaller.
   Shed the `qdbus6` and `journalctl` dependencies from the install script.

## What I'd build first

If we decide to proceed, my recommended ordering:

1. Harden the POC into `research/vscode_ipc.py` that's import-safe from
   the main launcher — no side effects at import, typed signatures.
2. Write unit tests against a fake server (easy — it's just bytes in and
   bytes out).
3. Sketch a `VSCodeIPCInspector` adapter class that produces the same
   shape the current `WindowScanner` produces, so it's a drop-in.
4. A/B the two backends behind a `VSCODE_LAUNCHER_BACKEND=ipc|kwin` env
   var for a few days.
5. If the IPC backend is reliable, flip the default and deprecate KWin.

Happy to do any subset of the above next session. The hard work — reverse
engineering the protocol to the point where a Python client round-trips
cleanly in 3 ms — is done.
