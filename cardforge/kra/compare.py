"""Image comparison that ignores colour data hidden under transparency.

Krita keeps stale RGB in pixels it has erased to alpha 0; our writer drops
fully transparent tiles. The results render identically, so equivalence is
defined as: identical alpha everywhere, and identical RGB wherever alpha > 0.
"""
from __future__ import annotations

from PIL import Image, ImageChops


def visually_equal(a: Image.Image, b: Image.Image) -> bool:
    if a.size != b.size:
        return False
    a, b = a.convert("RGBA"), b.convert("RGBA")
    if ImageChops.difference(a.getchannel("A"), b.getchannel("A")).getbbox() is not None:
        return False
    mask = a.getchannel("A").point(lambda v: 255 if v else 0)
    black = Image.new("RGB", a.size, (0, 0, 0))
    va = Image.composite(a.convert("RGB"), black, mask)
    vb = Image.composite(b.convert("RGB"), black, mask)
    # alpha_only defaults to True on RGBA; these are RGB so all bands count.
    return ImageChops.difference(va, vb).getbbox() is None
