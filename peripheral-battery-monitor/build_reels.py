#!/usr/bin/env python3
"""Build LCD photo reels for the Kraken's round 640x640 panel.

Run after adding or reframing photos:

    ./build_reels.py            # rebuild every reel
    ./build_reels.py corgis     # just one

Why the reels look the way they do
----------------------------------
**Author at 640, not 480.** The driver resizes every frame to the panel's
640x640 *in palette mode* - nearest neighbour - and re-encodes. Feeding it a
480px source therefore does not save anything: the upscale invents noise that
will not delta-encode, and costs more than the smaller source saved. Measured on
corgis at identical settings: 480 source 28.25MB, 640 source 20.43MB.

An earlier version of this file advised shrinking the source to buy frames. That
was measured on the file on disk rather than on what the driver actually sends,
and it is backwards.

**One palette for the whole reel.** `convert("P", palette=ADAPTIVE)` gives every
frame its own colour table, so consecutive frames cannot delta-encode - which is
precisely what a crossfade needs. Quantising every frame onto a single shared
palette took the same reel from 20.43MB to 14.17MB. 64 colours with
Floyd-Steinberg dithering is visually indistinguishable here from 96.

**Per-frame durations.** A held photo is one frame carrying the whole hold
(Pillow merges identical consecutive frames and sums their duration), and each
crossfade step carries only FADE_MS. With one global duration, a fade could be
made smoother only by making it slower; separating them buys smoothness for
free. This is what fixed transitions that looked "very chunky": corgis went from
5 crossfade steps to 24 at the same 0.84s transition.

**The budget is the real ceiling.** liquidctl asserts the re-encoded GIF is
under 24.32MB (`_LCD_TOTAL_MEMORY`), so frames are the currency and crossfades
spend nearly all of them. Reels differ in length, so `build` steps the fade count
down from MAX_FADE until it fits rather than using a fixed value that would waste
headroom on short reels and overrun on long ones.

**Smoothness costs upload time.** Push is roughly 1.5s fixed plus 0.22s per MB,
and the panel is *blank for the whole transfer*. A smoother reel means a longer
black gap on every scene change - about 5.8s for a 19.6MB reel against 4.0s for
an 11MB one. That is the trade, and it is the only real argument for restraint.

**The loop is seamless by construction.** The last photo crossfades back into the
first, which is where the GIF restarts. Verified by comparing the RMS pixel
difference across the wrap against the median difference between adjacent frames:
the seam is smaller than an ordinary fade step in every reel.

**The panel is round.** A plain centre crop decapitated several subjects, so
every photo carries a hand-chosen crop centre in CENTRES, picked by eye from a
contact sheet rendered with the circular cut-off dimmed. Photos are indexed by
position in the sorted source listing, so adding files shifts the indices -
re-check the framing when the set changes.
"""

import glob
import io
import os
import sys

from PIL import Image, ImageOps, ImageSequence

SRC = os.path.expanduser("~/Dropbox/Documents/iphoto_exports")
OUT = os.path.expanduser("~/Pictures/LcdAnimations")

SIZE = 640            # the panel's native size - see "Author at 640" below
FRAME_MS = 180        # per-frame hold; the speed dial
FADE_MS = 35          # per-frame during a crossfade; smoothness, not duration
MAX_FADE = 28         # ceiling on crossfade steps; each reel fits under this
MIN_FADE = 6          # below this a dissolve reads as a slideshow again
COLORS = 64
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
    "corgis":   ([1, 2, 5, 9, 10, 12], 16, 5),
    "cats":     ([0, 7, 11], 30, 8),
    "puppies":  ([12, 2, 1], 30, 8),
    "everyone": ([8, 2, 11, 10, 7, 4, 9, 0], 12, 4),
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


def render(imgs, hold, fade) -> tuple[list, list]:
    """Frames and per-frame durations for one reel.

    The loop is seamless by construction: the last photo crossfades back into
    imgs[0], which is where the GIF restarts.

    Durations are per frame, not global. A held photo is one frame carrying the
    whole hold, and each crossfade step carries only FADE_MS - so smoothness and
    pacing stop fighting each other. With a single global duration a fade could
    only be made smoother by making it slower.
    """
    frames, durs = [], []
    for i, im in enumerate(imgs):
        nxt = imgs[(i + 1) % len(imgs)]
        # One held frame, not `hold` copies: Pillow merges identical consecutive
        # frames and sums their duration, so emitting copies just wasted work.
        frames.append(im.copy())
        durs.append(FRAME_MS * hold)
        for k in range(fade):
            frames.append(Image.blend(im, nxt, (k + 1) / (fade + 1)))
            durs.append(FADE_MS)
    return frames, durs


def quantise(frames) -> list:
    """Map every frame onto ONE palette.

    Per-frame ADAPTIVE palettes were costing about a third of the file. Each
    frame then carries its own colour table and cannot delta-encode against its
    neighbour, which is exactly what a crossfade needs to do.
    """
    base = frames[0].quantize(colors=COLORS, method=Image.MEDIANCUT)
    return [f.quantize(colors=COLORS, palette=base,
                       dither=Image.Dither.FLOYDSTEINBERG) for f in frames]


def write(dst, pal, durs):
    os.makedirs(OUT, exist_ok=True)
    pal[0].save(dst, save_all=True, append_images=pal[1:], duration=durs,
                loop=0, optimize=True)


def build(name, idxs, hold, fade=MAX_FADE) -> str:
    """Build `name`, using the smoothest crossfade that fits the budget.

    `fade` is a ceiling rather than a setting. Reels differ in length - three
    photos to eight - so one fixed value either wastes headroom on the short
    reels or overruns on the long ones. Stepping down from the ceiling spends
    whatever each reel has.
    """
    paths = photos()
    imgs = [square(paths, i) for i in idxs]
    dst = f"{OUT}/{name}.gif"
    budget = LIMIT_BYTES * SAFETY

    for attempt in range(fade, MIN_FADE - 1, -2):
        frames, durs = render(imgs, hold, attempt)
        pal = quantise(frames)
        write(dst, pal, durs)
        size = encoded_size(dst)
        if size <= budget:
            secs = sum(durs) / 1000
            print(f"  {name+'.gif':16} {len(idxs)} photos  {len(pal):>3} frames  "
                  f"{attempt:>2} fade steps  {size/1e6:>5.1f}MB on device  "
                  f"{secs:>5.1f}s loop  ({attempt*FADE_MS/1000:.2f}s fades, "
                  f"~{1.5 + 0.22*size/1e6:.1f}s blank on push)")
            return dst

    os.unlink(dst)
    raise SystemExit(
        f"{name}: will not fit {budget/1e6:.1f}MB even at {MIN_FADE} fade steps; "
        f"drop a photo or shorten the hold")


def main(argv):
    wanted = argv or list(REELS)
    unknown = [w for w in wanted if w not in REELS]
    if unknown:
        raise SystemExit(f"unknown reel(s): {', '.join(unknown)}")
    for name in wanted:
        build(name, *REELS[name][:2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
