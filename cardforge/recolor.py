"""Exact accent recolouring for two-tone line art.

Card frames are drawn in black plus a single accent colour. Rather than
storing one asset per palette, an asset is stored once and declares which
colour is swappable; every pixel is treated as a blend ``C = t * accent``,
and recolouring replaces it with ``t * new_accent``.

Alpha is never touched, so anti-aliased edges survive exactly and a no-op
recolour returns the original bytes unchanged.
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def parse_hex(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def to_hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def retint(img: Image.Image, src, dst) -> Image.Image:
    """Replace accent colour `src` with `dst`, preserving blends and alpha."""
    if isinstance(src, str):
        src = parse_hex(src)
    if isinstance(dst, str):
        dst = parse_hex(dst)
    if tuple(src) == tuple(dst):
        return img.copy()

    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    rgb = a[..., :3]
    src_a = np.array(src, dtype=np.float32)
    dst_a = np.array(dst, dtype=np.float32)

    # Recover the blend factor from whichever channels actually carry the
    # accent; a pure-black pixel gives t = 0 and is left alone.
    strong = np.flatnonzero(src_a > 8)
    if len(strong) == 0:
        return img.copy()
    t = np.clip(np.stack([rgb[..., c] / src_a[c] for c in strong], axis=-1).max(-1), 0, 1)

    out = a.copy()
    out[..., :3] = t[..., None] * dst_a
    return Image.fromarray(np.rint(out).astype(np.uint8), "RGBA")


def tint_mask(mask: Image.Image, rgb) -> Image.Image:
    """Colour a black-on-transparent mask, keeping its alpha shape."""
    if isinstance(rgb, str):
        rgb = parse_hex(rgb)
    out = Image.new("RGBA", mask.size, tuple(rgb) + (0,))
    out.putalpha(mask.convert("RGBA").getchannel("A"))
    return out
