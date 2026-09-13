"""Assemble a .kra document from a stack of layers.

Layers are given bottom-first, the same order Krita lists them in
maindoc.xml. Paint layers carry a full-canvas RGBA image; vector layers
carry an SVG string.
"""
from __future__ import annotations

import io
import uuid as _uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from PIL import Image

from .image import image_to_tiles
from .tiles import write_layer

MIMETYPE = b"application/x-krita"
DEFAULT_PROFILE = "sRGB-elle-V2-srgbtrc.icc"


@dataclass
class PaintLayer:
    name: str
    image: Image.Image            # full-canvas RGBA
    visible: bool = True
    opacity: int = 255
    composite: str = "normal"


@dataclass
class VectorLayer:
    name: str
    svg: str
    visible: bool = True
    opacity: int = 255
    composite: str = "normal"


@dataclass
class Document:
    width: int
    height: int
    name: str = "Card"
    dpi: float = 300.0
    profile: str = DEFAULT_PROFILE
    icc: bytes = b""
    layers: list = field(default_factory=list)   # bottom-first

    @property
    def size(self):
        return (self.width, self.height)

    def flatten(self) -> Image.Image:
        canvas = Image.new("RGBA", self.size, (0, 0, 0, 0))
        for layer in self.layers:
            if not layer.visible or not isinstance(layer, PaintLayer):
                continue
            src = layer.image
            if layer.opacity < 255:
                src = src.copy()
                src.putalpha(src.getchannel("A").point(
                    lambda v, o=layer.opacity: v * o // 255))
            canvas.alpha_composite(src)
        return canvas

    def save(self, path, merged: Image.Image | None = None) -> None:
        if merged is None:
            merged = self.flatten()
        preview = merged.copy()
        preview.thumbnail((256, 256))

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            # The mimetype entry must be first and stored uncompressed.
            z.writestr(zipfile.ZipInfo("mimetype"), MIMETYPE,
                       compress_type=zipfile.ZIP_STORED)
            z.writestr("maindoc.xml", self._maindoc())
            z.writestr("documentinfo.xml", self._documentinfo())
            z.writestr("preview.png", _png(preview))
            z.writestr("mergedimage.png", _png(merged))
            if self.icc:
                z.writestr(f"{self.name}/annotations/icc", self.icc)
            z.writestr(f"{self.name}/animation/index.xml", _ANIMATION)

            for i, layer in enumerate(self.layers, start=2):
                base = f"{self.name}/layers/layer{i}"
                if isinstance(layer, PaintLayer):
                    z.writestr(base, write_layer(image_to_tiles(layer.image)))
                    z.writestr(base + ".defaultpixel", b"\x00\x00\x00\x00")
                    if self.icc:
                        z.writestr(base + ".icc", self.icc)
                else:
                    z.writestr(base + ".shapelayer/content.svg", layer.svg)

    def _maindoc(self) -> str:
        rows = []
        for i, layer in enumerate(self.layers, start=2):
            common = (
                f'filename="layer{i}" name="{_esc(layer.name)}" '
                f'compositeop="{layer.composite}" opacity="{layer.opacity}" '
                f'visible="{1 if layer.visible else 0}" '
                f'uuid="{{{_uuid.uuid4()}}}" '
                f'locked="0" collapsed="0" colorlabel="0" x="0" y="0" channelflags=""'
            )
            if isinstance(layer, PaintLayer):
                rows.append(f'   <layer {common} nodetype="paintlayer" '
                            f'colorspacename="RGBA" channellockflags="1111" '
                            f'onionskin="0" intimeline="1"/>')
            else:
                rows.append(f'   <layer {common} nodetype="shapelayer" intimeline="0"/>')
        layers_xml = "\n".join(rows)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE DOC PUBLIC '-//KDE//DTD krita 2.0//EN' 'http://www.calligra.org/DTD/krita-2.0.dtd'>
<DOC xmlns="http://www.calligra.org/DTD/krita" kritaVersion="5.2.2" syntaxVersion="2.0" editor="Krita">
 <IMAGE colorspacename="RGBA" name="{_esc(self.name)}" description="" mime="application/x-kra" \
height="{self.height}" profile="{self.profile}" width="{self.width}" \
y-res="{self.dpi:g}" x-res="{self.dpi:g}">
  <layers>
{layers_xml}
  </layers>
  <ProjectionBackgroundColor ColorData="AAAAAA=="/>
  <GlobalAssistantsColor SimpleColorData="176,176,176,255"/>
  <Palettes/>
  <resources/>
  <animation>
   <framerate value="24" type="value"/>
   <range to="100" from="0" type="timerange"/>
   <currentTime value="0" type="value"/>
  </animation>
 </IMAGE>
</DOC>
"""

    def _documentinfo(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE document-info PUBLIC '-//KDE//DTD document-info 1.1//EN' 'http://www.calligra.org/DTD/document-info-1.1.dtd'>
<document-info xmlns="http://www.calligra.org/DTD/document-info">
 <about>
  <title>{_esc(self.name)}</title>
  <description></description>
  <subject></subject>
  <abstract><![CDATA[]]></abstract>
  <keyword></keyword>
  <initial-creator>cardforge</initial-creator>
  <editing-cycles>1</editing-cycles>
  <editing-time>0</editing-time>
  <date>{now}</date>
  <creation-date>{now}</creation-date>
  <language></language>
  <license></license>
 </about>
 <author><full-name></full-name></author>
</document-info>
"""


_ANIMATION = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE animation-metadata PUBLIC '-//KDE//DTD krita 1.1//EN' 'http://www.calligra.org/DTD/krita-1.1.dtd'>
<animation-metadata xmlns="http://www.calligra.org/DTD/krita">
 <framerate value="24" type="value"/>
 <range to="100" from="0" type="timerange"/>
 <currentTime value="0" type="value"/>
 <export-settings>
  <sequenceFilePath value="" type="value"/>
  <sequenceBaseName value="" type="value"/>
  <sequenceInitialFrameNumber value="-1" type="value"/>
 </export-settings>
</animation-metadata>
"""


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
