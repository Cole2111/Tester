"""Krita paint-layer tile serialisation.

A paint-layer file is a small text header followed by one blob per tile:

    VERSION 2
    TILEWIDTH 64
    TILEHEIGHT 64
    PIXELSIZE 4
    DATA <tile count>
    <x>,<y>,LZF,<byte count>\\n<blob>

Tile coordinates are multiples of the tile size in layer space; the layer's
own x/y offset from maindoc.xml is added on top. Inside a blob the first
byte is a compression flag (1 = LZF) and the payload is *planar*: all blue
bytes, then all green, then red, then alpha. Planar ordering is what makes
flat-colour line art compress so well.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import lzf

TILE_W = TILE_H = 64
PIXEL_SIZE = 4


@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    rgba: bytes          # TILE_W * TILE_H * 4, interleaved RGBA


def _planar_to_rgba(plane: bytes, npx: int) -> bytes:
    b, g, r, a = (plane[i * npx:(i + 1) * npx] for i in range(4))
    out = bytearray(npx * 4)
    out[0::4] = r
    out[1::4] = g
    out[2::4] = b
    out[3::4] = a
    return bytes(out)


def _rgba_to_planar(rgba: bytes) -> bytes:
    return bytes(rgba[2::4]) + bytes(rgba[1::4]) + bytes(rgba[0::4]) + bytes(rgba[3::4])


def read_layer(raw: bytes) -> tuple[int, int, list[Tile]]:
    pos = 0
    header: dict[str, str] = {}
    for _ in range(5):
        eol = raw.index(b"\n", pos)
        key, value = raw[pos:eol].decode().split(" ", 1)
        header[key] = value
        pos = eol + 1

    tw, th = int(header["TILEWIDTH"]), int(header["TILEHEIGHT"])
    ps, count = int(header["PIXELSIZE"]), int(header["DATA"])
    if ps != PIXEL_SIZE:
        raise ValueError(f"unsupported pixel size {ps} (only 8-bit RGBA is handled)")

    npx = tw * th
    tiles = []
    for _ in range(count):
        eol = raw.index(b"\n", pos)
        sx, sy, _compression, ssize = raw[pos:eol].decode().split(",")
        pos = eol + 1
        size = int(ssize)
        blob, pos = raw[pos:pos + size], pos + size
        payload = lzf.decompress(blob[1:], npx * ps) if blob[0] == 1 else blob[1:]
        tiles.append(Tile(int(sx), int(sy), _planar_to_rgba(payload, npx)))
    return tw, th, tiles


def write_layer(tiles: list[Tile], tw: int = TILE_W, th: int = TILE_H) -> bytes:
    out = bytearray(
        b"VERSION 2\n"
        b"TILEWIDTH %d\nTILEHEIGHT %d\nPIXELSIZE %d\nDATA %d\n"
        % (tw, th, PIXEL_SIZE, len(tiles))
    )
    for tile in tiles:
        planar = _rgba_to_planar(tile.rgba)
        packed = lzf.compress(planar)
        # LZF can inflate incompressible data; fall back to a raw blob.
        blob = b"\x01" + packed if len(packed) < len(planar) else b"\x00" + planar
        out += b"%d,%d,LZF,%d\n" % (tile.x, tile.y, len(blob))
        out += blob
    return bytes(out)
