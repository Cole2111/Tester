"""Round-trip tests against the real Krita template."""
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cardforge.kra import Document, KraDocument, PaintLayer, VectorLayer
from cardforge.kra.compare import visually_equal
from cardforge.kra.image import image_to_tiles, tiles_to_image
from cardforge.kra.lzf import compress, decompress
from cardforge.kra.tiles import read_layer, write_layer

TEMPLATE = os.environ.get("CARDFORGE_TEMPLATE", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "beta-frame.kra"))
needs_template = pytest.mark.skipif(
    not os.path.exists(TEMPLATE), reason="template .kra not available")


@pytest.mark.parametrize("data", [
    b"", b"a", b"\x80\x00\x00\x00\x00", b"\x00" * 70000,
    bytes(range(256)) * 64, b"hello world " * 5000, os.urandom(40000),
])
def test_lzf_roundtrip(data):
    assert decompress(compress(data), len(data)) == data


def test_lzf_never_emits_short_match_as_literal():
    """A 2-byte match encodes to a control byte < 32, which decodes as a
    literal run. Regression guard for that whole class of corruption."""
    for n in range(1, 15):
        for bits in range(1 << n):
            b = bytes(0xFF if (bits >> i) & 1 else 0x00 for i in range(n))
            assert decompress(compress(b), len(b)) == b


def test_tiles_skip_transparent_regions():
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (10, 10, 40, 40))
    tiles = image_to_tiles(img)
    assert len(tiles) == 1 and (tiles[0].x, tiles[0].y) == (0, 0)
    assert visually_equal(tiles_to_image(tiles, img.size), img)


@needs_template
def test_every_template_layer_reencodes_bit_exactly():
    src = KraDocument(TEMPLATE)
    for layer in (l for l in src.layers if l.is_paint):
        tw, th, tiles = read_layer(src.raw(layer))
        tw2, th2, again = read_layer(write_layer(tiles, tw, th))
        assert (tw, th) == (tw2, th2)
        assert [(t.x, t.y, t.rgba) for t in tiles] == [(t.x, t.y, t.rgba) for t in again]


@needs_template
def test_document_write_read_preserves_all_layers(tmp_path):
    src = KraDocument(TEMPLATE)
    doc = Document(src.width, src.height, name="RoundTrip", dpi=src.x_res,
                   profile=src.profile, icc=src.icc())
    expected = []
    for layer in src.layers:
        if layer.is_paint:
            img = src.render(layer)
            expected.append(img)
            doc.layers.append(PaintLayer(layer.name, img, visible=layer.visible,
                                         opacity=layer.opacity,
                                         composite=layer.composite))
        else:
            doc.layers.append(VectorLayer(layer.name, src.svg(layer),
                                          visible=layer.visible))
    out = tmp_path / "out.kra"
    doc.save(out)

    back = KraDocument(out)
    assert back.size == src.size
    assert len(back.layers) == len(src.layers)
    painted = [l for l in back.layers if l.is_paint]
    assert len(painted) == len(expected)
    for layer, want in zip(painted, expected):
        assert visually_equal(back.render(layer), want), layer.name
    vectors = [l for l in back.layers if l.is_vector]
    assert len(vectors) == len([l for l in src.layers if l.is_vector])
    assert all("<svg" in back.svg(l) for l in vectors)


@needs_template
def test_mimetype_is_first_and_stored(tmp_path):
    import zipfile
    src = KraDocument(TEMPLATE)
    doc = Document(64, 64, name="Tiny", icc=src.icc())
    doc.layers.append(PaintLayer("only", Image.new("RGBA", (64, 64), (1, 2, 3, 255))))
    out = tmp_path / "tiny.kra"
    doc.save(out)
    with zipfile.ZipFile(out) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/x-krita"


def test_retint_noop_is_exact():
    import numpy as np
    from cardforge.recolor import retint
    img = Image.new("RGBA", (8, 8))
    img.putdata([(0, 173, 255, 255), (0, 86, 128, 200), (0, 0, 0, 255),
                 (0, 0, 0, 0)] * 16)
    assert np.array_equal(np.asarray(retint(img, "#00ADFF", "#00ADFF")),
                          np.asarray(img))


def test_retint_preserves_alpha_and_pure_black():
    import numpy as np
    from cardforge.recolor import retint
    img = Image.new("RGBA", (8, 8))
    img.putdata([(0, 173, 255, 255), (0, 86, 128, 200), (0, 0, 0, 255),
                 (0, 0, 0, 0)] * 16)
    out = retint(img, "#00ADFF", "#E03A1E")
    a, b = np.asarray(img).astype(int), np.asarray(out).astype(int)
    assert np.array_equal(a[..., 3], b[..., 3])
    pure = (a[..., :3].max(axis=2) == 0)
    assert np.array_equal(a[pure][:, :3], b[pure][:, :3])
    # a 50% blend of black and the accent stays a 50% blend of the new accent
    assert tuple(out.getpixel((1, 0)))[:3] == (112, 29, 15)


def test_retint_full_accent_becomes_new_accent():
    from cardforge.recolor import retint
    img = Image.new("RGBA", (2, 2), (0, 173, 255, 255))
    assert tuple(retint(img, "#00ADFF", "#E03A1E").getpixel((0, 0))) == (224, 58, 30, 255)
