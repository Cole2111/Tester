#!/usr/bin/env python3
"""Harvest a Krita card template into a modular asset library.

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
    "layer31": ("frames/beta", "frame", "accent"),    # two-tone; accent recoloured at composite time
    "layer33": ("frames/beta", "parchment", "flat"),  # keep full colour
    "layer32": ("frames/beta", "edge-runes", "mask"),
    "layer8":  ("frames/beta", "speck-a", "mask"),
    "layer10": ("frames/beta", "speck-b", "mask"),
    "layer30": ("frames/beta", "speck-c", "mask"),

    "layer16": ("elements", "ice", "mask"),           # confirmed: snowflake
    "layer15": ("elements", "unnamed-diamond", "mask"),
    "layer17": ("elements", "unnamed-slashes", "mask"),
    "layer18": ("elements", "unnamed-star", "mask"),
    "layer19": ("elements", "unnamed-swirl", "mask"),
    "layer21": ("elements", "unnamed-flame", "mask"),
    "layer27": ("elements", "unnamed-smoke", "mask"),

    "layer23": ("types", "unnamed-anvil", "mask"),    # visible on this card
    "layer22": ("types", "unnamed-figures", "mask"),
    "layer24": ("types", "unnamed-fist", "mask"),
    "layer25": ("types", "unnamed-swirl", "mask"),
    "layer28": ("types", "unnamed-eye", "mask"),

    "layer20": ("symbols", "aec-multiplier", "mask"),
    "layer14": ("symbols", "aec-plain", "mask"),

    "layer26": ("parts", "orb", "flat"),
    "layer29": ("parts", "stat-plate", "flat"),
    "layer34": ("parts", "art-placeholder", "mask"),
}

NEUTRAL_TOLERANCE = 40      # how far from grey a pixel may be and still be "ink"


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

    for filename, (folder, stem, mode) in HARVEST_MAP.items():
        layer = by_file.get(filename)
        if layer is None:
            print(f"  !! {filename} missing from template", file=sys.stderr)
            continue
        img = doc.render(layer)
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
