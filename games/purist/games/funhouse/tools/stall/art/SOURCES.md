# Ornament source art — provenance and licence

## Panel ornament — REMOVED (kept as a record of what was tried)
The banners now wear the sign board's own livery: maroon with gold lining, no motif.

Racinet's *Polychromatic Ornament* (1877, Plate IX — public domain, Racinet d.1893) was used for a
while as panel scrollwork, keyed over the livery. It was only ever a STAND-IN: **no fairground panel
art exists in the public domain.** Sheffield's National Fairground and Circus Archive — the one real
repository of British showmen's panel art — is all-rights-reserved, and everything on Wikimedia under
carousels is modern CC-BY-SA 3D photography. Borrowed Greco-Roman scrollwork read less like a real
stall than the signwritten board does, so it went.

If it is ever wanted back:
`https://iiif.archive.org/iiif/polychromaticor00raci$107/full/3276,/0/default.jpg` (native is
3276x5007 — check `info.json`; fetching smaller and upscaling invents pixels). Its "black" ground is
litho ink at LINEAR luminance ~0.20, not 0 — key from ~0.215, or it paints the plate's dark ground
over the livery at half opacity and everything reads muddy brown.

### Licence traps found while looking
- **Strong, *Book of Designs* (1917)** — the best stylistic match, but joint author L. S. Strong died
  1977, so UK PD is **2048**. "Pre-1929" is a US test; the UK runs author's death + 70.
- **Fred Fowle** lived 1914-1983 → UK PD 2054. Technique is not copyrightable; his marbling can be
  reproduced from PD sources.
- **CC-BY-SA** — rejected on principle: baked into a shared GLB the obligation becomes inseparable
  from our own art.

## The lamp — modelled, not sourced
A glass orb + an amber emissive filament, built in `build_stall.py` (~180 tris), instanced ~310x.

**There is no CC0 fairground cabochon anywhere.** Every Sketchfab `cabochon` hit is CC-BY-NC or
CC-BY-SA jewellery at 80k-2M tris. The only clean CC0 lamp that exists is Poly Haven `lightbulb_01`
(https://polyhaven.com/a/lightbulb_01, CC0) — a whole incandescent at 4372 tris, cap and coil and
wires. At 45mm across a dark stall none of that survives being looked at, so it was dropped: an orb
and a filament say the same thing for a fraction of the triangles, and owe nobody anything.

### Licence trap — do not use
Sketchfab **"CC0 - Light Bulb"** by plaggy is *titled* CC0 but its actual licence field reads
CC-Attribution, with no CC0 waiver text anywhere on the model. A title is not a licence grant.
Sketchfab's CC0 *category filter* is likewise unreliable — verify each model's own licence field.
