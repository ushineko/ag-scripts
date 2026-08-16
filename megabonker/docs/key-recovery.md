# Recovering the Megabonk save key

Megabonk encrypts `progression.json` and `stats.json` with an AES-256 key and IV
that are **compile-time constants baked into the game binary**. They are stable
for a given build and can rotate whenever the game updates. When that happens
every key in `megabonker/keys.py` stops working and saves will not open.

This document covers three things: the format, how to re-derive the constants
with the shipped tooling, and how to redo the work by hand if the automated
search ever fails.

## Contents

- [Save format](#save-format)
- [Current constants](#current-constants)
- [Re-deriving with megabonker](#re-deriving-with-megabonker)
- [How the search works](#how-the-search-works)
- [Doing it by hand](#doing-it-by-hand)
- [IL2CPP metadata reference](#il2cpp-metadata-reference)
- [If the scheme itself changes](#if-the-scheme-itself-changes)

## Save format

```
base64( AES-256-CBC( PKCS7( UTF-8 JSON ) ) )
```

| Property | Value |
| :--- | :--- |
| Cipher | AES-256, CBC mode |
| Padding | PKCS7 |
| IV | Hardcoded constant, **not** random per file and **not** prefixed to the ciphertext |
| Encoding | Base64, single line, no trailing newline |
| Plaintext | Pretty-printed JSON, 2-space indent |

Because the IV is fixed, encryption is deterministic: identical plaintext always
produces identical ciphertext. That is a real weakness in the game's design, but
for our purposes it is useful — it means re-encrypting an unmodified save
reproduces the original file byte for byte, which `megabonker` uses as a safety
check (`crypto.round_trip_ok`) before it is willing to write anything back.

Only the two `CloudDir` files are encrypted. `LocalDir/config.json` and
`controller_config.json` are plain JSON.

## Current constants

Recovered 2026-08-15 from the Feb-2026 Linux build (Steam appid 3405340):

```
key = d940840d5ae7c7907b092437bc0c5b44aaf70e273e12d0fb4da2b8c767cc911d
iv  = 37864ef15c24bc0acbc60e3978ef1f06
```

Both live in `global-metadata.dat`, in the field/parameter default-value blob —
the section where C# `new byte[]{...}` initialisers are stored:

| Constant | Location |
| :--- | :--- |
| Key (32 bytes) | `fieldAndParameterDefaultValueData` + 195872 (absolute file offset 7065536) |
| IV (16 bytes) | `fieldAndParameterDefaultValueData` + 195976 (absolute file offset 7065640) |

They sit 104 bytes apart, which is a useful sanity signal: if a future search
finds a key but no IV nearby, be suspicious of the result.

## Re-deriving with megabonker

The fast path. Both routes need the game installed and at least one encrypted
save file; supply two saves if you can, because the search is dramatically more
trustworthy when a candidate has to satisfy two independent ciphertexts.

**GUI** — Tools → Recover Save Key → Start Search. On success, "Save Key &
Reload" writes it to the keyring and reopens the saves.

**CLI**:

```bash
./megabonker.py derive-key --save
```

Useful flags:

| Flag | Purpose |
| :--- | :--- |
| `--game-dir DIR` | Point at the install if Steam library autodetection fails |
| `--profile DIR` | Choose the save profile to test against |
| `--save` | Add the recovered pair to `~/.config/megabonker/keys.json` |
| `--build LABEL` | Tag the keyring entry with a game build for later reference |
| `--exhaustive` | Drop the randomness pre-filter (see below); much slower |

A successful run takes well under a second and prints where each constant was
found:

```
key = d940840d5ae7c7907b092437bc0c5b44aaf70e273e12d0fb4da2b8c767cc911d
iv  = 37864ef15c24bc0acbc60e3978ef1f06
key found at defaultvalues+195872
iv  found at defaultvalues+195976
```

Verify before trusting it:

```bash
./megabonker.py list          # every save should report OK
```

## How the search works

The obvious approaches do not work here. The key is never a string, so grepping
finds nothing, and the assembly is name-obfuscated (identifiers look like
`AESDPrssBtHJkbTyoMyedzACHMdGc`), so there is no `SaveManager.Decrypt` to read.
Dumping the key at runtime with a debugger works but needs the game running and
a lot more scaffolding.

Instead the search is blind, and rests on two properties.

### 1. A candidate key can be tested without knowing the IV

In CBC, decryption of block *i* is `P[i] = D_K(C[i]) XOR C[i-1]`. The IV is only
needed for block 0. So for the **last** block:

```
P[n-1] = D_K(C[n-1]) XOR C[n-2]
```

Both `C[n-1]` and `C[n-2]` are sitting in the save file. That gives a scoring
function for any candidate key with no IV required: decrypt the last block and
check whether the result has valid PKCS7 padding over printable text.

One file alone is a weak test — random keys pass the padding check roughly 0.4%
of the time. Requiring the same key to pass on **two independent save files**
drops that to about 1 in 60,000, and adding the printable-text requirement makes
false positives effectively impossible.

> A subtlety worth preserving: strip the padding bytes *before* testing
> printability. PKCS7 values are 1–16, so a save whose plaintext happens to need
> a 9-byte pad has 9 non-printable bytes in its final block. An earlier version
> of this code used a fixed "at least 14 of 16 bytes printable" threshold and
> passed only by luck, because a 9-byte pad is `0x09` — a tab, which the
> printable set happened to include. A different plaintext length would have
> rejected the correct key. See `derive._tail_looks_like_json`.

### 2. Once the key is known, the IV falls out of known plaintext

With the key in hand, `D_K(C[0])` is a constant, and `P[0] = D_K(C[0]) XOR IV`.
We know the plaintext is JSON, so `P[0][0] == '{'`. Therefore:

```
IV = D_K(C[0]) XOR P[0]
```

Scan the binary for any 16-byte window that XORs the constant into printable
text beginning with `{`. Across 12 MB of metadata this yields exactly one hit,
which decodes to `{\n  "gold": 0,\n ` — a perfectly plausible JSON opening, so
it is clearly the real IV rather than a coincidence.

### Narrowing the candidate pool

Searching every byte offset is possible but slow in Python. Two rounds are done
in order:

1. **Random-looking windows.** An AES key is uniformly random and so has near
   maximal byte diversity, whereas metadata is overwhelmingly ASCII names, zero
   padding and small integers. Requiring ≥78% distinct bytes and ≤2 zero bytes
   cuts 540 KB of default-value data from ~540,000 candidate windows down to
   ~86,000, and the real key survives comfortably. This is what finds the key
   today, in about 0.9 seconds.
2. **String derivations.** Many Unity games do
   `Encoding.UTF8.GetBytes("somepassphrase")` or `MD5(password)` instead of a
   byte array. Every string literal and identifier in the metadata is tried as
   UTF-8 and UTF-16LE, raw and truncated, plus MD5 / SHA-1 / SHA-256 digests.
   (This found nothing for the current build — the key really is a byte array —
   but it is the first thing to check on a new build.)
3. **Exhaustive** (`--exhaustive`): every offset, no diversity filter. Reach for
   this only if the first two fail.

## Doing it by hand

If `derive-key` fails outright — the metadata format changed, the key moved to
the native binary, the cipher changed — here is the procedure from scratch. It
needs only Python with `cryptography` and `numpy`.

### Step 1: confirm the format

```python
import base64, collections, math
raw = open("progression.json","rb").read()
ct = base64.b64decode(raw)
print(len(ct), len(ct) % 16)                     # expect a multiple of 16
c = collections.Counter(ct)
ent = -sum(v/len(ct)*math.log2(v/len(ct)) for v in c.values())
print(f"{ent:.2f} bits/byte")                    # ~8.0 means encrypted
blocks = [ct[i:i+16] for i in range(0,len(ct),16)]
print("repeated blocks:", len(blocks)-len(set(blocks)))   # >0 hints at ECB
```

Block-aligned length plus ~8.0 bits/byte entropy means a block cipher with
padding. Zero repeated blocks rules out ECB over repetitive plaintext.

### Step 2: locate the metadata

```
<game>/Megabonk_Data/il2cpp_data/Metadata/global-metadata.dat
```

Check the header: the first four bytes must be `AF 1B B1 FA` (0xFAB11BAF
little-endian) and the next int32 is the format version. `megabonker` currently
understands version 29 and refuses anything else rather than searching the wrong
byte ranges — if the version has changed, confirm the section layout against the
Il2CppDumper source before proceeding.

### Step 3: run the oracle over candidate windows

```python
from megabonker.derive import key_fits, _targets, load_metadata_blobs
targets = _targets([open(p,"rb").read() for p in save_paths])
blobs = load_metadata_blobs(game_dir)
for name, blob in blobs.items():
    for i in range(len(blob)-32):
        for size in (32, 16):
            k = blob[i:i+size]
            if key_fits(k, targets):
                print("HIT", name, i, k.hex())
```

If the metadata yields nothing, widen to `GameAssembly.so` itself — the key may
have moved into `.rodata`. That file is ~87 MB, so apply the diversity
pre-filter (`derive._entropy_filtered_windows`) or expect a long wait.

### Step 4: recover the IV

```python
from megabonker.derive import recover_iv
print(recover_iv(key_bytes, open(save_path,"rb").read(), blobs))
```

If that returns nothing, the IV may not be a stored constant. Try, in order: an
all-zero IV; the first 16 bytes of the key; a 16-byte IV prefixed to the
ciphertext (in which case block 0 is the IV and real data starts at offset 16).
Distinguish these by checking whether the recovered plaintext starts with `{`.

### Step 5: validate before trusting

Never write a save with an unvalidated key. Two checks:

```python
json.loads(decrypt(blob, candidate))                  # decrypts to valid JSON
assert encrypt(decrypt(blob, candidate), candidate) == blob   # exact round-trip
```

The round-trip is the important one. It proves the mode, padding and IV are all
understood, not merely that the key produces plausible-looking output.
`SaveFile.load` runs it automatically and refuses to open any file that fails.

## IL2CPP metadata reference

`global-metadata.dat` opens with a sanity value, a version, then pairs of
`(offset, size)` int32s. Byte offsets of the pairs `megabonker` uses:

| Byte offset | Section | Contents |
| ---: | :--- | :--- |
| 0 | `sanity` | `0xFAB11BAF` |
| 4 | `version` | format version (29 for this build) |
| 8 | `stringLiteral` | table of `(length, dataIndex)` pairs, 8 bytes each |
| 16 | `stringLiteralData` | the literal bytes, **no null separators** |
| 24 | `string` | identifier names, null-terminated |
| 72 | `fieldAndParameterDefaultValueData` | `byte[]` initialisers — **the key lives here** |

The literal blob storing lengths in a side table rather than using null
terminators is worth knowing: running `strings` over it returns giant
concatenated runs rather than individual literals, which is misleading. Parse
the table instead (`derive.load_metadata_strings`).

## If the scheme itself changes

If no key is found by any route, the encryption itself may have changed. Signals
and next steps:

| Observation | Likely meaning |
| :--- | :--- |
| Ciphertext length no longer a multiple of 16 | Stream cipher or a mode without padding (CTR/CFB/OFB) |
| Length is plaintext + 28 or similar | AES-GCM (12-byte nonce + 16-byte tag) |
| Two saves with identical content differ | Random per-file IV, probably prefixed to the ciphertext |
| Base64 no longer decodes | Raw binary, or a different encoding entirely |
| Decoded data starts `1f 8b` or `78 9c` | Compressed before encryption (or instead of it) |

For a random-IV variant the last-block oracle still works unchanged — that is
the whole point of using the *last* block — so `key_fits` remains valid and only
`recover_iv` needs replacing with "read the first 16 bytes of the file".

If the game moves to a key derived at runtime (from the Steam ID, a server
response, or a KDF over hardware identifiers), static recovery stops working and
the only route is dumping the key from a running process. That is out of scope
for this tool.
