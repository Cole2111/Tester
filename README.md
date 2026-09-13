# cardforge

Generates Krita (`.kra`) card files from plain-text card data, by compositing
a library of swappable PNG assets.

Status: **codec and asset pipeline working.** The card compositor, text
layout, and local web UI are not built yet.

## The asset model

Nothing about a card's appearance is hard-coded. Every non-text element is a
PNG in `assets/`, and the filename stem is the value card data matches on --
so adding an element means dropping in a file, not editing code.

```
assets/
  frames/beta/   frame.png, parchment.png, edge-runes.png, speck-*.png
  elements/      ice.png, ... (one per element symbol)
  types/         one per card-type symbol
  symbols/       aec-multiplier.png, aec-plain.png
  parts/         orb.png, stat-plate.png, art-placeholder.png
  manifest.json  what was harvested, from which source layer
```

Assets are **full-canvas transparent PNGs**, so position is baked into the
image. A replacement drops in at the right place with no coordinates to
configure.

### Colour is not an asset

Symbols are stored as black-on-transparent **masks** and tinted at composite
time, so one `ice.png` serves every palette.

Two-tone line art (the frame) is stored **unmodified**, declaring which colour
is swappable. Each pixel is read as a blend `C = t x accent` and rewritten as
`t x new_accent`. Alpha is never touched, so anti-aliased edges survive
exactly and recolouring to the same colour is a byte-for-byte no-op.

## Krita format support

`cardforge/kra/` is a dependency-free reader/writer for Krita documents:
tiled paint layers (64x64, planar BGRA), LZF compression, and vector layers
as SVG.

Verified against the real template: all 23 paint layers re-encode
**pixel-exact**, and output runs ~10% smaller than Krita's own files.

One deliberate difference: Krita keeps stale RGB in pixels erased to alpha 0.
Fully transparent tiles are dropped on write. Output renders identically;
`cardforge.kra.compare.visually_equal` encodes that equivalence.

## Usage

```sh
python3 tools/harvest.py templates/beta-frame.kra -o assets   # rebuild assets
python3 -m pytest tests/ -q                                   # run tests
```
