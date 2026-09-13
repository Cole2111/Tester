"""Bridge between Krita tile data and PIL images."""
from __future__ import annotations

from PIL import Image

from .tiles import TILE_H, TILE_W, Tile


def tiles_to_image(tiles: list[Tile], size: tuple[int, int],
                   offset: tuple[int, int] = (0, 0),
                   tile_size: tuple[int, int] = (TILE_W, TILE_H)) -> Image.Image:
    """Composite tiles onto a transparent canvas of `size`."""
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    for tile in tiles:
        patch = Image.frombytes("RGBA", tile_size, tile.rgba)
        canvas.paste(patch, (tile.x + offset[0], tile.y + offset[1]))
    return canvas


def image_to_tiles(img: Image.Image) -> list[Tile]:
    """Cut an RGBA image into tiles, skipping fully transparent ones."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    alpha = img.getchannel("A")
    tiles: list[Tile] = []
    for ty in range(0, h, TILE_H):
        for tx in range(0, w, TILE_W):
            box = (tx, ty, tx + TILE_W, ty + TILE_H)
            if alpha.crop(box).getbbox() is None:
                continue                      # nothing but transparency here
            patch = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
            patch.paste(img.crop(box), (0, 0))
            tiles.append(Tile(tx, ty, patch.tobytes()))
    return tiles
