#!/usr/bin/env python3
"""Command line entry point for megabonker.

With no arguments the GUI editor launches. The subcommands exist so saves can
be scripted, diffed and version-controlled without opening a window, and so the
key can be re-derived on a headless box.
"""

import argparse
import json
import os
import sys

from megabonker.crypto import DecryptError, encrypt, try_decrypt
from megabonker.derive import DeriveError, derive, find_game_dir
from megabonker.keys import SaveKey, load_keyring, save_key
from megabonker.savefile import (ENCRYPTED_NAMES, SAVE_ROOT, SaveError,
                                 find_profiles, save_roots)


def _resolve_profile(requested: str | None) -> str:
    """Return the profile directory to operate on, or exit with guidance."""
    if requested:
        if not os.path.isdir(requested):
            sys.exit(f"[ERROR] profile directory not found: {requested}")
        return requested
    profiles = find_profiles()
    if not profiles:
        sys.exit(f"[ERROR] no Megabonk profiles found under {SAVE_ROOT}")
    if len(profiles) > 1:
        names = ", ".join(steamid for steamid, _ in profiles)
        sys.exit(f"[ERROR] multiple profiles found ({names}); pick one with --profile")
    return profiles[0][1]


def cmd_list(args) -> int:
    """Show discovered profiles, save files and whether a key decrypts them."""
    profiles = find_profiles()
    if not profiles:
        print(f"No profiles found under {SAVE_ROOT}")
        return 1
    keyring = load_keyring()
    for origin, root in save_roots():
        print(f"Save root ({origin}): {root}")
    print(f"Keys available: {len(keyring)}")
    game_dir = find_game_dir()
    print(f"Game install: {game_dir or 'not found'}")
    for label, path in profiles:
        print(f"\nProfile {label}")
        for name in ENCRYPTED_NAMES:
            full = os.path.join(path, name)
            if not os.path.exists(full):
                continue
            try:
                _, used = try_decrypt(open(full, "rb").read(), keyring)
                status = f"OK via '{used.label}'"
            except DecryptError as e:
                status = f"FAILED ({e})"
            print(f"  {name:<20} {os.path.getsize(full):>7} bytes  {status}")
    return 0


def cmd_decrypt(args) -> int:
    """Decrypt a save file to readable JSON."""
    blob = open(args.file, "rb").read()
    try:
        plaintext, used = try_decrypt(blob)
    except DecryptError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    print(f"[INFO] decrypted with '{used.label}'", file=sys.stderr)
    if args.output:
        with open(args.output, "wb") as f:
            f.write(plaintext)
        print(f"[OK] wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(plaintext)
    return 0


def cmd_encrypt(args) -> int:
    """Re-encrypt plain JSON into the form the game reads."""
    plaintext = open(args.file, "rb").read()
    try:
        json.loads(plaintext)
    except ValueError as e:
        print(f"[ERROR] input is not valid JSON: {e}", file=sys.stderr)
        return 1
    keyring = load_keyring()
    chosen = keyring[0]
    if args.key and args.iv:
        chosen = SaveKey(key=args.key, iv=args.iv, label="command line")
    blob = encrypt(plaintext, chosen)
    if args.output:
        with open(args.output, "wb") as f:
            f.write(blob)
        print(f"[OK] wrote {args.output} using '{chosen.label}'", file=sys.stderr)
    else:
        sys.stdout.buffer.write(blob)
    return 0


def cmd_derive_key(args) -> int:
    """Recover the key and IV from the game's own files."""
    game_dir = args.game_dir or find_game_dir()
    if not game_dir:
        print("[ERROR] could not locate the Megabonk install; pass --game-dir",
              file=sys.stderr)
        return 1
    profile = _resolve_profile(args.profile)
    blobs = []
    for name in ENCRYPTED_NAMES:
        full = os.path.join(profile, name)
        if os.path.exists(full):
            blobs.append(open(full, "rb").read())
    if not blobs:
        print(f"[ERROR] no encrypted save files in {profile}", file=sys.stderr)
        return 1
    if len(blobs) == 1:
        print("[WARNING] only one save file available; a second file would make "
              "the result far more trustworthy", file=sys.stderr)

    print(f"[INFO] game:    {game_dir}", file=sys.stderr)
    print(f"[INFO] profile: {profile}", file=sys.stderr)

    state = {"stage": None}

    def progress(stage, done, total):
        if stage != state["stage"]:
            state["stage"] = stage
            print(f"[INFO] {stage}...", file=sys.stderr)

    try:
        result = derive(game_dir, blobs, progress=progress, exhaustive=args.exhaustive)
    except DeriveError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    if not result:
        print("[FAIL] no key found. Retry with --exhaustive; if that also fails "
              "the save format itself has changed.", file=sys.stderr)
        return 1

    print(f"\nkey = {result.key.hex()}")
    print(f"iv  = {result.iv.hex()}")
    print(f"key found at {result.key_location}", file=sys.stderr)
    print(f"iv  found at {result.iv_location}", file=sys.stderr)

    if args.save:
        sk = result.to_save_key(build=args.build)
        save_key(sk)
        print("[OK] added to the megabonker keyring", file=sys.stderr)
    else:
        print("[INFO] re-run with --save to add this to the keyring", file=sys.stderr)
    return 0


def cmd_gui(args) -> int:
    """Launch the editor."""
    try:
        from megabonker.gui.main_window import run
    except ImportError as e:
        print(f"[ERROR] GUI unavailable (is PyQt6 installed?): {e}", file=sys.stderr)
        return 1
    return run(profile=args.profile)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="megabonker",
        description="Megabonk save editor and key-recovery toolkit.",
    )
    sub = parser.add_subparsers(dest="command")

    p_gui = sub.add_parser("gui", help="launch the editor (default)")
    p_gui.add_argument("--profile", help="profile directory to open")
    p_gui.set_defaults(func=cmd_gui)

    p_list = sub.add_parser("list", help="show profiles and key status")
    p_list.set_defaults(func=cmd_list)

    p_dec = sub.add_parser("decrypt", help="decrypt a save file to JSON")
    p_dec.add_argument("file")
    p_dec.add_argument("-o", "--output", help="write here instead of stdout")
    p_dec.set_defaults(func=cmd_decrypt)

    p_enc = sub.add_parser("encrypt", help="encrypt JSON into a save file")
    p_enc.add_argument("file")
    p_enc.add_argument("-o", "--output", help="write here instead of stdout")
    p_enc.add_argument("--key", help="override key (64 hex chars)")
    p_enc.add_argument("--iv", help="override IV (32 hex chars)")
    p_enc.set_defaults(func=cmd_encrypt)

    p_der = sub.add_parser("derive-key",
                           help="recover the key and IV from the game files")
    p_der.add_argument("--game-dir", help="Megabonk install directory")
    p_der.add_argument("--profile", help="profile directory to test against")
    p_der.add_argument("--exhaustive", action="store_true",
                       help="skip the randomness pre-filter (much slower)")
    p_der.add_argument("--save", action="store_true",
                       help="add the recovered key to the keyring")
    p_der.add_argument("--build", default="", help="label the game build")
    p_der.set_defaults(func=cmd_derive_key)
    return parser


def main() -> int:
    # Double-click and menu launches arrive with no arguments; open the GUI.
    if len(sys.argv) == 1:
        sys.argv.append("gui")
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except (SaveError, OSError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
