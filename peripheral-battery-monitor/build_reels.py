#!/usr/bin/env python3
"""Build LCD photo reels for the Kraken's round 640x640 panel.

Run after adding or reframing photos:

    ./build_reels.py            # rebuild every reel
    ./build_reels.py corgis     # just one

Why the parameters are what they are
------------------------------------
**Frame budget.** liquidctl asserts a GIF is under 24MB *after* it resizes to
the panel's 640x640 — about 0.3MB a frame — so a reel has roughly 65 frames to
spend. That is the hard constraint everything else bends around.

**Slowness comes from duration, not frames.** Wanting a slower reel is really
wanting more seconds per photo, and frames cannot buy them. So FRAME_MS is the
dial, and ZOOM_AMOUNT is deliberately small: a big zoom spread over few frames
judders once each frame is held a quarter of a second.

**The panel is round.** A plain centre crop decapitated several subjects, so
each photo carries a hand-chosen crop centre, picked by eye from a contact
sheet rendered with the circular cut-off dimmed.
"""

import glob
import os
import sys

from PIL import Image, ImageOps

SRC = os.path.expanduser("~/Dropbox/Documents/iphoto_exports")
OUT = os.path.expanduser("~/Pictures/LcdAnimations")

SIZE = 480            # liquidctl upscales to the panel's 640x640
FRAME_MS = 260        # per-frame hold; the main speed dial
ZOOM_AMOUNT = 0.06    # push-in over a photo's hold, kept subtle at this cadence
MAX_FRAMES = 64       # stay under the driver's 24MB post-resize assert
COLORS = 96

# Crop centre per photo index, as a fraction of width/height.
CENTRES = {
    0: (0.42, 0.40), 1: (0.50, 0.56), 2: (0.50, 0.50), 3: (0.50, 0.50),
    4: (0.55, 0.58), 5: (0.50, 0.52), 6: (0.50, 0.50), 7: (0.48, 0.55),
    8: (0.50, 0.46), 9: (0.50, 0.50), 10: (0.45, 0.55), 11: (0.50, 0.56),
    12: (0.50, 0.52),
}

# name -> (photo indices, hold frames, fade frames)
REELS = {
    "corgis":   ([1, 2, 5, 9, 10, 12], 6, 4),
    "cats":     ([0, 7, 11], 11, 6),
    "puppies":  ([12, 2, 1], 11, 6),
    "everyone": ([8, 2, 11, 10, 7, 4, 9, 0], 5, 3),
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


def zoomed(im, t):
    s = im.size[0]
    c = int(s * (1.0 - ZOOM_AMOUNT * t))
    off = (s - c) // 2
    return im.crop((off, off, off + c, off + c)).resize((SIZE, SIZE), Image.LANCZOS)


def build(name, idxs, hold, fade) -> str:
    paths = photos()
    frames_planned = len(idxs) * (hold + fade)
    if frames_planned > MAX_FRAMES:
        raise SystemExit(
            f"{name}: {frames_planned} frames exceeds the {MAX_FRAMES} budget; "
            f"drop a photo or shorten hold/fade")

    imgs = [square(paths, i) for i in idxs]
    frames = []
    span = hold + fade - 1
    for i, im in enumerate(imgs):
        nxt = imgs[(i + 1) % len(imgs)]
        for k in range(hold):
            frames.append(zoomed(im, k / span))
        for k in range(fade):
            frames.append(Image.blend(zoomed(im, (hold + k) / span),
                                      zoomed(nxt, 0.0), (k + 1) / (fade + 1)))

    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=COLORS) for f in frames]
    dst = f"{OUT}/{name}.gif"
    os.makedirs(OUT, exist_ok=True)
    pal[0].save(dst, save_all=True, append_images=pal[1:], duration=FRAME_MS,
                loop=0, optimize=True)
    secs = len(pal) * FRAME_MS / 1000
    print(f"  {name+'.gif':16} {len(idxs)} photos  {len(pal)} frames  "
          f"{os.path.getsize(dst)//1024} KB  {secs:.0f}s loop "
          f"({secs/len(idxs):.1f}s per photo)")
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
