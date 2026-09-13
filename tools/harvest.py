#!/usr/bin/env python3
"""Harvest a Krita card template into a modular asset library.

How each asset must be stored is measured from its pixels, not declared.

Every non-text layer becomes a full-canvas transparent PNG. Positions are
baked into the canvas, so dropping in a replacement PNG needs no coordinates
and no metadata edit -- the file itself is the configuration.

Flat-colour line art is split by colour: black strokes become a `-mask` PNG
that the compositor tints at runtime, so one asset serves every palette.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cardforge.kra import KraDocument     # noqa: E402
from cardforge.recolor import to_hex     # noqa: E402

# Provisional slot names. Rename the PNGs to rename the options -- the
# filename stem is the value the card data matches on.
HARVEST_MAP = {
    "layer31": ("frames/beta", "frame"),    # two-tone; accent recoloured at composite time
    "layer33": ("frames/beta", "parchment"),  # keep full colour
    "layer32": ("frames/beta", "edge-runes"),
    "layer8": ("frames/beta", "speck-a"),
    "layer10": ("frames/beta", "art-window-fill"),

    "layer16": ("elements", "ice"),           # confirmed: snowflake
    "layer15": ("elements", "unnamed-diamond"),
    "layer17": ("elements", "unnamed-slashes"),
    "layer18": ("elements", "unnamed-star"),
    "layer19": ("elements", "unnamed-swirl"),
    "layer21": ("elements", "unnamed-flame"),
    "layer27": ("elements", "unnamed-smoke"),

    "layer23": ("types", "unnamed-anvil"),    # visible on this card
    "layer22": ("types", "unnamed-figures"),
    "layer24": ("types", "unnamed-fist"),
    "layer25": ("types", "unnamed-swirl"),
    "layer28": ("types", "unnamed-eye"),

    "layer20": ("symbols", "aec-multiplier"),
    "layer14": ("symbols", "aec-plain"),

    "layer26": ("parts", "orb"),
    "layer29": ("parts", "stat-plate"),
    "layer34": ("parts", "art-placeholder"),
}

NEUTRAL_TOLERANCE = 40      # how far from grey a pixel may be and still be "ink"
INK_LEVEL = 60              # RGB at or below this counts as a black stroke


def classify(img: Image.Image) -> str:
    """Decide how an asset must be stored, by looking at its pixels.

    mask   - every visible pixel is a black stroke; safe to recolour wholesale
    accent - black strokes plus one saturated colour (two-tone line art)
    flat   - anything else (texture, white fill); stored as-is, never tinted

    Guessing this by eye is how a white-filled layer ends up stored as a
    black mask and paints a solid block over the card.
    """
    a = np.asarray(img.convert("RGBA")).astype(np.int16)
    visible = a[..., 3] > 16
    if not visible.any():
        return "empty"
    rgb = a[..., :3][visible]
    ink = (rgb.max(axis=1) <= INK_LEVEL).mean()
    saturated = ((rgb.max(axis=1) - rgb.min(axis=1)) > NEUTRAL_TOLERANCE).mean()
    if ink > 0.97:
        return "mask"
    if saturated > 0.02 and ink + saturated > 0.95:
        return "accent"
    return "flat"


def dominant_accent(img: Image.Image) -> tuple[int, int, int]:
    """The most common strongly-saturated colour in a two-tone layer."""
    a = np.asarray(img, dtype=np.int16)
    rgb, alpha = a[..., :3], a[..., 3]
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    sel = rgb[(alpha > 128) & (chroma > NEUTRAL_TOLERANCE)]
    if not len(sel):
        return (0, 0, 0)
    sel = sel.astype(np.int32)   # int16 overflows on the << 8 shift
    packed = (sel[:, 0] << 16) | (sel[:, 1] << 8) | sel[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    top = int(values[counts.argmax()])
    return ((top >> 16) & 255, (top >> 8) & 255, top & 255)


def to_mask(img: Image.Image) -> Image.Image:
    """Force every visible pixel to black, preserving the alpha shape."""
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.putalpha(img.getchannel("A"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("template", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("assets"))
    args = ap.parse_args()

    doc = KraDocument(args.template)
    by_file = {l.filename: l for l in doc.layers}
    manifest: dict = {
        "source": args.template.name,
        "canvas": {"width": doc.width, "height": doc.height, "dpi": doc.x_res},
        "assets": {},
    }
    palette_hint = None

    for filename, (folder, stem) in HARVEST_MAP.items():
        layer = by_file.get(filename)
        if layer is None:
            print(f"  !! {filename} missing from template", file=sys.stderr)
            continue
        img = doc.render(layer)
        mode = classify(img)
        if mode == "empty":
            print(f"  {filename:>8} -- empty layer, skipped")
            continue
        target = args.out / folder
        target.mkdir(parents=True, exist_ok=True)

        if mode == "accent":
            accent = dominant_accent(img)
            palette_hint = to_hex(accent)
            img.save(target / f"{stem}.png")          # stored unmodified
            written = [f"{folder}/{stem}.png"]
            print(f"  {filename:>8} -> {folder}/{stem}.png "
                  f"(two-tone, accent {palette_hint})")
        elif mode == "mask":
            to_mask(img).save(target / f"{stem}.png")
            written = [f"{folder}/{stem}.png"]
            print(f"  {filename:>8} -> {folder}/{stem}.png (tintable mask)")
        else:
            img.save(target / f"{stem}.png")
            written = [f"{folder}/{stem}.png"]
            print(f"  {filename:>8} -> {folder}/{stem}.png (flat colour)")

        manifest["assets"][filename] = {
            "slot": folder, "name": stem, "mode": mode,
            "source_layer": layer.name, "visible_in_template": layer.visible,
            "bbox": img.getbbox(alpha_only=True), "files": written,
        }

    manifest["accent"] = palette_hint
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nmanifest -> {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
