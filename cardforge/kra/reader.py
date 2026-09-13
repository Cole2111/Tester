"""Read a .kra document: layer metadata, pixels, and vector SVG."""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field

from PIL import Image

from .image import tiles_to_image
from .tiles import read_layer


@dataclass
class Layer:
    filename: str                 # "layer31"
    name: str                     # "Paint Layer 1"
    nodetype: str                 # paintlayer | shapelayer | ...
    visible: bool
    opacity: int
    composite: str
    x: int
    y: int
    uuid: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def is_paint(self) -> bool:
        return self.nodetype == "paintlayer"

    @property
    def is_vector(self) -> bool:
        return self.nodetype == "shapelayer"


class KraDocument:
    def __init__(self, path):
        self.path = str(path)
        self.zip = zipfile.ZipFile(self.path)
        self.maindoc = self.zip.read("maindoc.xml").decode("utf-8")

        img_tag = re.search(r"<IMAGE\b[^>]*>", self.maindoc).group(0)
        attrs = dict(re.findall(r'(\S+)="([^"]*)"', img_tag))
        self.name = attrs["name"]
        self.width = int(attrs["width"])
        self.height = int(attrs["height"])
        self.x_res = float(attrs.get("x-res", 300))
        self.y_res = float(attrs.get("y-res", 300))
        self.profile = attrs.get("profile", "")

        self.layers: list[Layer] = []
        for match in re.finditer(r"<layer\b[^>]*/>", self.maindoc):
            a = dict(re.findall(r'(\S+)="([^"]*)"', match.group(0)))
            self.layers.append(Layer(
                filename=a.get("filename", ""),
                name=a.get("name", ""),
                nodetype=a.get("nodetype", ""),
                visible=a.get("visible", "1") == "1",
                opacity=int(a.get("opacity", 255)),
                composite=a.get("compositeop", "normal"),
                x=int(a.get("x", 0)),
                y=int(a.get("y", 0)),
                uuid=a.get("uuid", ""),
                extra=a,
            ))

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def _path(self, layer: Layer, suffix: str = "") -> str:
        return f"{self.name}/layers/{layer.filename}{suffix}"

    def raw(self, layer: Layer) -> bytes:
        return self.zip.read(self._path(layer))

    def render(self, layer: Layer) -> Image.Image:
        """Render one paint layer onto a full-canvas transparent image."""
        if not layer.is_paint:
            raise TypeError(f"{layer.name} is a {layer.nodetype}, not a paint layer")
        tw, th, tiles = read_layer(self.raw(layer))
        return tiles_to_image(tiles, self.size, (layer.x, layer.y), (tw, th))

    def svg(self, layer: Layer) -> str:
        return self.zip.read(self._path(layer, ".shapelayer/content.svg")).decode("utf-8")

    def icc(self) -> bytes:
        try:
            return self.zip.read(f"{self.name}/annotations/icc")
        except KeyError:
            return b""

    def merged(self) -> Image.Image:
        import io
        return Image.open(io.BytesIO(self.zip.read("mergedimage.png"))).convert("RGBA")
