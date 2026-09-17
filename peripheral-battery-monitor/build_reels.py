#!/usr/bin/env python3
"""Build LCD photo reels for the Kraken's round 640x640 panel.

Run after adding or reframing photos:

    ./build_reels.py            # rebuild every reel
    ./build_reels.py corgis     # just one

Why the reels look the way they do
----------------------------------
**What spends the budget.** liquidctl re-encodes the GIF at the panel's 640x640
and asserts the result is under 24MB. What matters is how well *that* re-encode
compresses, and GIF delta-encodes between frames. Measured on this content:

    zoom on every frame   0.304 MB/frame   ->  80 frames
    static hold           0.058 MB/frame   -> 418 frames
    static + crossfade    0.185 MB/frame   -> 131 frames

A continuous pan/zoom resamples every pixel of every frame, so nothing
delta-encodes and it burns the entire budget on motion. Held frames are five
times cheaper. So each photo is held perfectly still and the budget goes into
long, smooth crossfades, which is where motion actually reads.

Shrinking the source was the other candidate — 240px instead of 480px buys about
18% more frames — but it softens family photos for a fraction of what dropping
the zoom gives, so the reels stay at 480.

**Slowness is duration; smoothness is frames.** FRAME_MS sets seconds per photo.
HOLD and FADE set how long a photo rests and how smoothly it dissolves.

**The panel is round.** A plain centre crop decapitated several subjects, so
every photo carries a hand-chosen crop centre in CENTRES, picked by eye from a
contact sheet rendered with the circular cut-off dimmed. Photos are indexed by
position in the sorted source listing, so adding files shifts the indices —
re-check the framing when the set changes.
"""

import glob
import io
import os
import sys

from PIL import Image, ImageOps, ImageSequence

SRC = os.path.expanduser("~/Dropbox/Documents/iphoto_exports")
OUT = os.path.expanduser("~/Pictures/LcdAnimations")

SIZE = 480            # liquidctl upscales to the panel's 640x640
FRAME_MS = 180        # per-frame hold; the speed dial
COLORS = 96
# Measured, not guessed: build() weighs each reel through the driver's own
# encoder. The driver's assert is fatal, so keep headroom under it.
LIMIT_BYTES = 24320 * 1000
SAFETY = 0.85

# Crop centre per photo index, as a fraction of width/height.
CENTRES = {
    0: (0.42, 0.40), 1: (0.50, 0.56), 2: (0.50, 0.50), 3: (0.50, 0.50),
    4: (0.55, 0.58), 5: (0.50, 0.52), 6: (0.50, 0.50), 7: (0.48, 0.55),
    8: (0.50, 0.46), 9: (0.50, 0.50), 10: (0.45, 0.55), 11: (0.50, 0.56),
    12: (0.50, 0.52),
}

# name -> (photo indices, static hold frames, crossfade frames)
REELS = {
    "corgis":   ([1, 2, 5, 9, 10, 12], 16, 8),
    "cats":     ([0, 7, 11], 30, 14),
    "puppies":  ([12, 2, 1], 30, 14),
    "everyone": ([8, 2, 11, 10, 7, 4, 9, 0], 12, 6),
}


def photos() -> list[str]:
    return sorted(glob.glob(f"{SRC}/*.jpeg")) + sorted(glob.glob(f"{SRC}/*.jpg"))


def square(paths, idx):
    im = ImageOps.exif_transpose(Image.open(paths[idx])).convert("RGB")
    w, h = im.size
    s = min(w, h)
    fx, fy = CENTRES.get(idx, (0.5, 0.5))
    cx, cy = int(w * fx), int(h * fy)
    left = max(0, min(w - s, cx - s // 2))
    top = max(0, min(h - s, cy - s // 2))
    return im.crop((left, top, left + s, top + s)).resize((SIZE, SIZE), Image.LANCZOS)


def encoded_size(path: str) -> int:
    """Bytes as the driver will measure them: re-encoded at 640x640.

    Replicates KrakenZ3._prepare_gif_file, so a reel is weighed exactly the way
    the hardware weighs it rather than against a frame count that happened to
    work for different content.
    """
    img = Image.open(path)
    frames = (f.copy().resize((640, 640)) for f in ImageSequence.Iterator(img))
    first = next(frames)
    first.info = img.info
    buf = io.BytesIO()
    first.save(buf, format="GIF", interlace=False, save_all=True,
               append_images=list(frames), loop=0)
    return len(buf.getvalue())


def build(name, idxs, hold, fade) -> str:
    paths = photos()
    imgs = [square(paths, i) for i in idxs]

    frames = []
    for i, im in enumerate(imgs):
        nxt = imgs[(i + 1) % len(imgs)]
        # Identical frames delta-encode to almost nothing; that is what pays for
        # the long crossfade that follows.
        frames.extend(im.copy() for _ in range(hold))
        frames.extend(Image.blend(im, nxt, (k + 1) / (fade + 1)) for k in range(fade))

    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=COLORS) for f in frames]
    dst = f"{OUT}/{name}.gif"
    os.makedirs(OUT, exist_ok=True)
    pal[0].save(dst, save_all=True, append_images=pal[1:], duration=FRAME_MS,
                loop=0, optimize=True)

    size = encoded_size(dst)
    budget = LIMIT_BYTES * SAFETY
    if size > budget:
        os.unlink(dst)
        raise SystemExit(
            f"{name}: {size/1e6:.1f}MB re-encoded at 640x640 exceeds the "
            f"{budget/1e6:.1f}MB working budget; shorten hold/fade or drop a photo")

    secs = len(pal) * FRAME_MS / 1000
    print(f"  {name+'.gif':16} {len(idxs)} photos  {len(pal):>3} frames  "
          f"{size/1e6:>5.1f}MB on device  {secs:>5.1f}s loop  "
          f"({secs/len(idxs):.1f}s per photo, {fade*FRAME_MS/1000:.1f}s fades)")
    return dst


def main(argv):
    wanted = argv or list(REELS)
    unknown = [w for w in wanted if w not in REELS]
    if unknown:
        raise SystemExit(f"unknown reel(s): {', '.join(unknown)}")
    for name in wanted:
        build(name, *REELS[name])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
