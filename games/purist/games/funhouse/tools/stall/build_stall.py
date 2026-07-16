"""Headless-Blender: travelling fairground ROUND STALL (hoopla), built from researched construction.

  blender --background --python build_stall.py -- <out.glb>

Deterministic + self-contained: builds the whole stall from the constants below and writes a GLB with
its OWN materials + embedded textures. No in-place mutation, no external mesh input.

Construction notes (sources in the research brief):
  * 10 convex shutters (NOT a hexagon - hexagons are modern event-hire stock, absent from the record).
    6" bow on the chord; the shutter ring is the structure, the legs are light.
  * Fairground paint = translucent flamboyant glaze over aluminium leaf, built up 12-80+ coats, varnished.
    -> modelled as coloured METAL (metallic~1, low roughness). It reflects the lamps; that is the look.
  * Cabochons (45mm) face-drilled through a lampboard at 80mm centres, 2700K.
  * Wear = ~1,300 erection cycles, not 40 years of weather. It is carried by the REAL scans (scratches,
    scuffs, worn paint, AO) rather than procedural noise - fbm grime read as painted-on dirt and fought
    the real ornament. What stays procedural: varnish amber, and the canopy's stripes + storage creases.
"""
import bpy, bmesh, sys, math, os, tempfile
import numpy as np
from mathutils import Vector, Matrix

# ---------------------------------------------------------------- researched parameters (metres)
# CAM_FIT compresses the PLAN and the ABOVE-COUNTER height for camera framing. It is 1.0 (real size)
# because the real 14'9" stall was measured to frame correctly: against the game camera (CameraOrbit
# Fov 55 VERTICAL, orbit 25-105cm, elevation 10 to -80) the cabochon ring is fully in shot at max
# zoom-out, and spectacular when the player pitches up. The lights can never appear at DEFAULT zoom
# (60cm/35deg) at ANY stall size - pitched down 35 with a 27.5 half-FOV, the top of frame is 7.5 BELOW
# horizontal, so nothing above eye height is visible. That is the camera, not the model; shrinking the
# stall or raising the table cannot buy it (the table would need to be ~2.3m high).
#
# COUNTER_H and SKIRT_H are never scaled: anthropometric, and the manifest's -85cm drop is what lands
# the board exactly on the counter. The cabochons keep their real 45mm/80mm spec.
SIDES        = 10       # 10 (or 8). Hexagon = modern hire-stock invention; set to 6 only under protest.
CAM_FIT      = 1.0      # 1.0 = real 4.50m across flats. Dial down to compress for framing.
REAL_FLATS, REAL_EAVES, REAL_APEX = 4.50, 2.30, 3.66

COUNTER_H    = 0.85                                          # real, unscaled - the board sits on this
SKIRT_H      = 0.724                                         # 28.5" shutter, unscaled (below counter)
ACROSS_FLATS = REAL_FLATS * CAM_FIT
EAVES_H      = COUNTER_H + (REAL_EAVES - COUNTER_H) * CAM_FIT
APEX_H       = COUNTER_H + (REAL_APEX - COUNTER_H) * CAM_FIT
OVERHANG     = 0.60 * CAM_FIT    # ~2ft eaves overhang
POST         = 0.06              # light leg section
BEAM_W       = 0.05              # eaves beam ring capping the pillars - the bulb ring mounts
BEAM_H       = 0.08              # on its INSIDE face
FASCIA_H     = 0.32 * CAM_FIT    # lampboard / valance depth
HUB          = 0.16 * CAM_FIT    # crown boss the rafters land into
CAB_D        = 0.045    # 45mm cabochon - REAL fixture size, not scaled
CAB_PITCH    = 0.08     # 80mm centres  - REAL fixture spacing, not scaled
TEX          = 1024
# Was 2048 to carry the Racinet motif at its native ~989 px/m. The motif is gone, and nothing left on
# a painted surface needs that: back to TEX.
PANEL_TEX    = 1024
# Normals ship at HALF TEX. They must stay PNG (JPEG's chroma subsampling wrecks a normal map), which
# made them the single biggest block in the GLB - and a normal map is the map that tolerates low
# resolution best: it carries slope, not detail the eye reads directly.
NRM_TEX      = 512

# Keep's enamel range (Fowle's palette), as flamboyant glazes over leaf.
KEEPS = {
    "kingsway_red":  (0.62, 0.045, 0.035),
    "chrome_yellow": (0.86, 0.52,  0.02),
    "empire_blue":   (0.03, 0.11,  0.42),
    "empire_green":  (0.02, 0.26,  0.13),
    "fast_cerise":   (0.60, 0.03,  0.20),
}
TIMBER = (0.30, 0.20, 0.12)
GOLD   = (0.85, 0.62, 0.22)   # gold leaf: lining, beading, signwriting
SIGN   = "CARROM"
FONT_PATH = "C:/Windows/Fonts/georgiab.ttf"

argv = sys.argv[sys.argv.index("--") + 1:]
OUT  = argv[0]
TMP  = tempfile.mkdtemp(prefix="stall_tex_")
RNG  = np.random.default_rng(7)          # fixed seed -> byte-identical rebuilds

A  = ACROSS_FLATS / 2.0                          # apothem
R  = A / math.cos(math.pi / SIDES)               # circumradius
BULB_R = R + OVERHANG

bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------------------------------------------------------- real scanned source textures
# Every surface is grounded in a photoscan; the procedural layer only does livery + ornament + wear.
# The painted-timber scan is pulled from the TRACKED coin GLB - the loose meshes/*.jpg beside it are
# gitignored Extract-Textures artifacts and would not survive a fresh clone.
# Every source is inside THIS repo - the engine is a consumer of content, never a build dependency of it.
HERE     = os.path.dirname(os.path.abspath(__file__))
SRC_GLB  = os.path.normpath(os.path.join(HERE, "..", "..", "assets", "meshes", "coin_black.glb"))
TBL_GLB  = os.path.normpath(os.path.join(HERE, "..", "..", "assets", "meshes", "table.glb"))
# The shared rough-timber PBR set. Neutral, so it tints cleanly to any livery - which is exactly how
# table.glb skins its wood. Lives in the engine's shared assets/ (which ship with the engine, not the
# content packs), so this is the one build-time path outside this repo.
ENGINE_T = "C:/Users/User/Documents/GitHub/Carrom-Engine/assets/textures"


def _img_np(im, size, tw=None, th=None):
    """size = square target; or pass tw/th for a non-square one."""
    w, h = im.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(buf)
    a = buf.reshape(h, w, 4)[:, :, :3]
    tw = tw or size; th = th or size
    if h != th or w != tw:
        a = a[np.ix_(np.linspace(0, h - 1, th).astype(int), np.linspace(0, w - 1, tw).astype(int))]
    return np.ascontiguousarray(a)


def load_file(path, size, noncolor=False):
    im = bpy.data.images.load(path)
    if noncolor: im.colorspace_settings.name = 'Non-Color'
    a = _img_np(im, size)
    bpy.data.images.remove(im)
    return a


for _g in (SRC_GLB, TBL_GLB):
    bpy.ops.import_scene.gltf(filepath=_g)
_src_imgs = {im.name: im for im in bpy.data.images if im.size[0]}
SCAN = {n: _img_np(im, TEX) for n, im in _src_imgs.items()}
# Sample the panel inputs at PANEL_TEX while the source images are still loaded (natively 2048).
CHIP_COL = _img_np(_src_imgs["plane_DefaultMaterial_BaseColor"], PANEL_TEX)   # REAL chipped paint
CHIP_NRM = _img_np(_src_imgs["plane_DefaultMaterial_Normal"], PANEL_TEX)
CHIP_RGH = _img_np(_src_imgs["plane_DefaultMaterial_Roughness"], PANEL_TEX)[:, :, 0]
# CRITICAL: drop the imported coin/table meshes. numpy copies survive; leaving them in the scene
# exports a carrom coin and the whole table INTO this GLB - +14k faces and ~33MB of their scans.
bpy.ops.wm.read_factory_settings(use_empty=True)

LUM = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def detail_of(arr):
    """Scan luminance normalised to mean 1.0 -> a pure modulation carrying the real brush streaks,
    scratches and tonal drift, which can then be applied under ANY livery colour."""
    d = arr @ LUM
    return d / max(float(d.mean()), 1e-4)


PAINT_DET = detail_of(SCAN["ColorRed"])          # painted timber: brushwork + scratches
# Cloth detail repeats on its own pitch on top of the per-bay UV. The stripes are drawn at their own
# frequency in the same texture and are unaffected by this.
CANVAS_DET = None            # set once tile_map is defined (below)
PAINT_NRM = SCAN["NormalGL"]                     # real 2048 surface relief
PAINT_RGH = SCAN["Roughness"][:, :, 0]


# Panel ornament: real PD chromolithograph (Racinet 1877 Pl.IX). Authored 2:1 landscape and stretched
# into the square texture, because the shutter UV maps that square back onto a ~2:1 panel - so it
# lands at its true proportion on the mesh. See art/SOURCES.md for provenance + licence reasoning.


# Panel paint: the real CHIPPED PAINT WOOD scan the table itself uses (table.glb's "Chipped Paint Wood"),
# tinted. A working top is plain trade paint knocked back to bare timber - no leaf under it - so the
# flamboyant treatment that suits the ornamented panels reads as orange plastic here. This is a real
# scan of that exact wear, and it tiles, so it also matches the table the board sits on.


def rgb2hsv(a):
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn
    hh = np.zeros_like(mx)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = d > 1e-6
    k = (mx == r) & m; hh[k] = ((g - b)[k] / d[k]) % 6
    k = (mx == g) & m; hh[k] = ((b - r)[k] / d[k]) + 2
    k = (mx == b) & m; hh[k] = ((r - g)[k] / d[k]) + 4
    return hh / 6.0, np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0), mx


def hsv2rgb(h, s, v):
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    i = (i % 6).astype(int)
    out = np.zeros(h.shape + (3,), np.float32)
    for k, (rr, gg, bb) in enumerate(((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))):
        m = i == k
        out[m] = np.stack([rr, gg, bb], -1)[m]
    return out


def recolour_paint(scan, target):
    """Carry a REAL chipped-paint scan to another livery by shifting its hue, keeping its own value and
    saturation STRUCTURE - so the chips, brush drift and worn streaks survive the recolour.

    This is the whole point: there is no photograph of "red paint" in a neutral grey scan multiplied by
    a colour - that gives flat, uniform, plastic paint. Real paint has to come from a photo of paint."""
    h, sa, v = rgb2hsv(scan)
    th, ts, tv = rgb2hsv(np.float32(target).reshape(1, 1, 3))
    mh, ms, mv = np.median(h), np.median(sa), np.median(v)
    h2 = (h + (float(th) - mh)) % 1.0                       # relative hue variation survives
    s2 = np.clip(sa * (float(ts) / max(ms, 1e-4)), 0, 1)
    v2 = np.clip(v * (float(tv) / max(mv, 1e-4)), 0, 1)
    return hsv2rgb(h2, s2, v2)


def tile_map(a, n):
    """Repeat a map n times across the texture, area-averaging DOWN first.

    Do NOT do this by sampling every nth texel: a scan's neighbouring texels are correlated (that is
    what makes it read as grain), and striding destroys that correlation, so the grain aliases into
    salt-and-pepper speckle - measurably WORSE the higher the tile factor. Note this only makes the
    features smaller; it cannot add detail, since texel density across the panel is fixed by TEX."""
    h = a.shape[0]
    m = h // n
    if a.ndim == 3:
        small = a[:m * n, :m * n].reshape(m, n, m, n, a.shape[2]).mean(axis=(1, 3))
        return np.ascontiguousarray(np.tile(small, (n, n, 1)))
    small = a[:m * n, :m * n].reshape(m, n, m, n).mean(axis=(1, 3))
    return np.ascontiguousarray(np.tile(small, (n, n)))


def fit(a, w, h):
    """Resample a square map into a w x h texture, area-averaging when shrinking so it does not alias.
    Lets a panel's texture match its ASPECT instead of wasting resolution on the short axis."""
    if a.shape[0] == h and a.shape[1] == w: return a
    fy = max(1, a.shape[0] // h); fx = max(1, a.shape[1] // w)
    if fy > 1 or fx > 1:
        ny, nx = a.shape[0] // fy, a.shape[1] // fx
        if a.ndim == 3:
            a = a[:ny * fy, :nx * fx].reshape(ny, fy, nx, fx, a.shape[2]).mean(axis=(1, 3))
        else:
            a = a[:ny * fy, :nx * fx].reshape(ny, fy, nx, fx).mean(axis=(1, 3))
    ys = np.linspace(0, a.shape[0] - 1, h).astype(int)
    xs = np.linspace(0, a.shape[1] - 1, w).astype(int)
    return np.ascontiguousarray(a[np.ix_(ys, xs)])


def downsample(a, size):
    """Area-average down to `size`. Used to keep the ORM/normal at TEX while the albedo runs at
    PANEL_TEX: only the COLOUR carries the motif, and the exporter merges AO into an ORM PNG per
    material - at 2048 that alone would be ~90MB of the GLB for detail nothing can see."""
    h = a.shape[0]
    f = h // size
    if f <= 1: return a
    if a.ndim == 3:
        return np.ascontiguousarray(a[:size * f, :size * f].reshape(size, f, size, f, a.shape[2]).mean(axis=(1, 3)))
    return np.ascontiguousarray(a[:size * f, :size * f].reshape(size, f, size, f).mean(axis=(1, 3)))


def tile_normal(a, n):
    """Tile a normal map, renormalising after the average so the vectors stay unit length."""
    t = tile_map(a, n) * 2 - 1
    return t / np.maximum(np.linalg.norm(t, axis=-1, keepdims=True), 1e-6) * 0.5 + 0.5


def blend_normals(base, det):
    """UDN blend: keep the ornament's macro slope, add the scan's micro slope."""
    a, b = base * 2 - 1, det * 2 - 1
    r = np.stack([a[..., 0] + b[..., 0], a[..., 1] + b[..., 1], a[..., 2] * b[..., 2]], -1)
    return r / np.maximum(np.linalg.norm(r, axis=-1, keepdims=True), 1e-6) * 0.5 + 0.5


# ---------------------------------------------------------------- procedural wear textures
def _vnoise(h, w, freq):
    """PERIODIC value noise - the lattice wraps, so the result tiles seamlessly. The counter repeats
    its texture ~24x around the ring; non-tiling noise would put a visible seam at every repeat."""
    g = RNG.random((freq, freq))
    ys = np.linspace(0, freq, h, endpoint=False); xs = np.linspace(0, freq, w, endpoint=False)
    yi = np.floor(ys).astype(int); xi = np.floor(xs).astype(int)
    y0, x0 = yi % freq, xi % freq
    y1, x1 = (yi + 1) % freq, (xi + 1) % freq
    fy = (ys - yi)[:, None]; fx = (xs - xi)[None, :]
    fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
    a = g[np.ix_(y0, x0)]; b = g[np.ix_(y0, x1)]
    c = g[np.ix_(y1, x0)]; d = g[np.ix_(y1, x1)]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(h, w, octaves=5, base=4):
    out = np.zeros((h, w)); amp = 1.0; tot = 0.0
    for o in range(octaves):
        out += amp * _vnoise(h, w, base * 2 ** o); tot += amp; amp *= 0.5
    return out / tot


def save(arr, name, jpeg=True):
    """Write an HxWx3 float array for Blender to embed. JPEG for colour/metallic/roughness (this GLB
    ships in a downloaded pack), PNG for normals - JPEG's chroma subsampling corrupts them."""
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(arr, 0, 1)
    img.pixels.foreach_set(rgba.ravel())
    ext = ".jpg" if jpeg else ".png"
    img.filepath_raw = os.path.join(TMP, name + ext)
    img.file_format = 'JPEG' if jpeg else 'PNG'
    img.save()
    return img.filepath_raw


def normal_from_height(hgt, strength=2.4):
    """Height field -> tangent-space normal. Carries the mouldings, lining relief and chip craters."""
    gy, gx = np.gradient(hgt.astype(np.float32))
    nx, ny = -gx * strength, -gy * strength
    nz = np.ones_like(nx)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l * 0.5 + 0.5, ny / l * 0.5 + 0.5, nz / l * 0.5 + 0.5], -1)


def pbr_set(name):
    """Load a shared PBR set using EVERY map it ships - colour, normal, roughness, AO, height and
    metalness. Casing is inconsistent across the sets, so each is probed.

    Height matters: glTF has no height/parallax slot, so a heightmap would simply be discarded. Folding
    its gradient into the normal keeps the MACRO relief (gouges, board steps) that a scanned normal
    alone tends to miss, which is most of what sells a surface as real at grazing angles."""
    d = f"{ENGINE_T}/{name}"

    def first(*names):
        for n in names:
            if os.path.exists(f"{d}/{n}"): return f"{d}/{n}"
        return None

    col = load_file(first("Color.jpg", "color.jpg"), TEX)
    nrm = load_file(first("NormalGL.jpg", "normalgl.jpg"), TEX, True)
    rgh = load_file(first("Roughness.jpg", "roughness.jpg", "Roughness.png"), TEX, True)[:, :, 0]
    ao_p, h_p, m_p = first("AO.jpg", "AO.png"), first("Height.png", "Displacement.jpg"), first("Metalness.jpg")
    ao  = load_file(ao_p, TEX, True)[:, :, 0] if ao_p else np.ones((TEX, TEX), np.float32)
    met = load_file(m_p, TEX, True)[:, :, 0] if m_p else None
    if h_p is not None:
        h = load_file(h_p, TEX, True)[:, :, 0]
        nrm = blend_normals(normal_from_height(h * 2.2, strength=1.5), nrm)
    # colour normalised to mean 1.0 -> pure scratch/scuff modulation that carries ANY tint truly
    det = col / np.maximum(col.mean(axis=(0, 1), keepdims=True), 1e-4)
    return dict(col=col, det=det, nrm=nrm, rgh=rgh, ao=ao, met=met)


CANVAS_DET = tile_map(PAINT_DET, 4)   # cloth drift, properly filtered - see tile_map
ROUGH = pbr_set("rough")     # neutral timber: counter, rafters, painted structure, panels
# The `rough` scan photographs ~1-2m of timber, so on a 1.46m shutter it is already near life-size:
# tile x1-2 reads as grain, x8 crushes its centimetre scratches to ~2mm and it reads as noise. (The
# earlier "repeat too low" was diagnosed against the COIN scan - a 3cm coin magnified ~50x across the
# panel - which is a different texture with the opposite problem.) Must divide TEX.
PANEL_VALUE = 0.48           # livery GROUND brightness. Applied before the ornament is composited,
#                              so it darkens the panel colour without dulling the scrollwork on top.
PANEL_METAL = 0.16           # flamboyant hint; 0.25 read as pastel
PANEL_TILE = 2
PANEL_NRM = tile_normal(CHIP_NRM, PANEL_TILE)
PANEL_RGH = tile_map(CHIP_RGH, PANEL_TILE)
BRASS = pbr_set("brass")     # real brass, with its own metalness map: gold leaf, signwriting, fixings


def _ellipse(u, v, cx, cy, a, b):
    return np.sqrt(((u - cx) / a) ** 2 + ((v - cy) / b) ** 2)


_NRM = {}


def paint_maps(name, rgb, neglected=False, ornament="lined", sign=None, shape=None):
    """Panel paint -> (albedo, orm, normal) paths.

    Wear comes from the REAL rough-timber scan - its own scratches, scuffs, grain and AO - tiled at
    PANEL_TILE so the detail is crisp rather than smeared across a 1.46m shutter. There is deliberately
    NO procedural grime here: fbm chalk, rain streaks, ring-strata chips and alligatoring all read as
    exactly what they were, painted noise, and they fought the real art on top.

    ornament: 'lined' = moulded frame + gold lining (shutters, counter trim, sign board).
              'none'  = plain paint (legs).
    neglected: the back of the stall - oldest paint, worst varnish, never repainted.
    """
    # shape=(w,h): a panel's texture should match its ASPECT. The lampboard bay is 5.7:1, so a square
    # map gives it 3200 px/m vertically (wasted) and only 560 px/m horizontally - the axis letterforms
    # actually need - and CARROM came out blurred.
    w, h = shape or (PANEL_TEX, PANEL_TEX)
    vv, uu = np.mgrid[0:h, 0:w]
    v = vv / float(h); u = uu / float(w)          # v=0 bottom .. 1 top
    col = np.clip(fit(tile_map(recolour_paint(CHIP_COL, rgb), PANEL_TILE), w, h) * PANEL_VALUE, 0, 1)
    # A HINT of metal: fairground paint is a glaze over leaf, so it should throw the lamps back. Kept
    # low - at 0.25 it stole enough from diffuse, and laid enough grey specular over the colour, to read
    # as pastel. It is affordable now only because the ground is darkened (PANEL_VALUE).
    metal = np.full((h, w), PANEL_METAL, dtype=np.float32)
    rough = np.clip(0.22 + fit(PANEL_RGH, w, h) * 0.55, 0.05, 1.0)
    hgt = np.zeros((h, w), dtype=np.float32)
    gold = np.float32(GOLD)

    # ---- ornament: without this it is a painted shed, not a fairground stall ----
    if ornament != "none":
        # Moulded frame: raised bead + inner gold lining. 12-80+ coats drown the arris, so the relief
        # is soft and rounded - never crisp - and the beading reads shallower than it was cut.
        # same rule as the banners: no sub-pixel lining, or it shimmers at grazing angles
        for inset, wdt, amp, is_gold in ((0.050, 0.016, 1.0, False), (0.085, 0.012, 0.55, True)):
            dx = np.minimum(u - inset, (1 - inset) - u)
            dy = np.minimum(v - inset, (1 - inset) - v)
            band = np.clip(1 - np.abs(np.minimum(dx, dy)) / wdt, 0, 1) ** 0.7
            hgt += band * amp
            if is_gold:
                g = np.clip((band - 0.14) / 0.52, 0, 1)          # wide soft ramp: survives minification
                col = col * (1 - g[..., None]) + gold * g[..., None]
                metal = metal * (1 - g) + 1.0 * g
                rough = rough * (1 - g) + 0.28 * g
    if sign:                                    # PRINTED signwriting - paint has no relief
        tm = text_mask(sign, 0.15, 1.83, FASCIA_H, res=(w, h))
        g = np.clip((tm - 0.25) / 0.35, 0, 1)
        col = col * (1 - g[..., None]) + gold * g[..., None]
        metal = metal * (1 - g) + 1.0 * g
        rough = rough * (1 - g) + 0.30 * g

    # varnish yellowing: an amber veil that lifts blacks + warms everything. Worst where never repainted.
    amber = np.array([1.06, 0.94, 0.66], dtype=np.float32)
    veil = 0.38 if neglected else 0.12
    col = np.clip(col * (1 - veil) + col * amber * veil, 0, 1)
    rough = np.clip(rough + 0.05 * veil, 0.05, 1.0)

    orm = downsample(np.stack([np.ones_like(rough), np.clip(rough, 0.05, 1.0),
                               np.clip(metal, 0, 1)], -1), TEX)
    # The normal depends only on the ornament tier - never on the livery colour - so one is shared per
    # tier. Nine copies of a 1024 PNG normal is ~20MB in a pack that ships over the wire.
    if ornament not in _NRM:
        _NRM[ornament] = save(fit(blend_normals(normal_from_height(hgt), fit(PANEL_NRM, w, h)),
                                  NRM_TEX, NRM_TEX), "nrm_" + ornament, jpeg=False)
    return save(col, name + "_col"), save(orm, name + "_orm"), _NRM[ornament]


def canvas_maps(name):
    """Tilt AND pelmet - one material, because they are the same proofed cloth.

    A showman's tilt is PROOFED canvas: waterproofed, so it reads as a slick shower-curtain sheen with
    soft folds. It is NOT a woven fabric - an exposed weave reads as sacking. Surface detail is only the
    faint drift of the paint scan; the form comes from the sag geometry and the storage creases.
    It is a 10-15yr consumable, so the NEWEST component: PVC plasticiser migrates out as a tacky film
    that grabs dirt, packing it into the permanent fold lines."""
    h = w = TEX
    v, u = np.mgrid[0:h, 0:w] / float(h)
    base = np.zeros((h, w, 3), dtype=np.float32)
    stripe = (np.floor(u * 4) % 2).astype(np.float32)             # 4 bands per bay = 40 around
    base[:] = np.float32([0.86, 0.84, 0.80])
    base[stripe > 0.5] = np.float32([0.52, 0.07, 0.07])
    base *= (0.88 + 0.12 * CANVAS_DET)[..., None]                # tight cloth drift - no weave
    grime = fbm(h, w, 5, 5)
    base *= (0.78 + 0.22 * grime)[..., None]
    lum = base @ LUM
    base = base * 0.80 + lum[..., None] * 0.20                   # greasy-grey cast
    fold = np.clip(1 - np.abs(((v * 7) % 1.0) - 0.5) * 13, 0, 1) # storage creases: geometric, permanent
    base *= (1 - fold * 0.13)[..., None]                         # dirt in the fold, not a stripe
    # Waterproof sheen: proofing sits ON the cloth, so it stays glossy except where grime/plasticiser
    # has gone tacky. Matte here would read as raw canvas.
    rough = np.clip(0.17 + grime * 0.13 + fold * 0.10 + (CANVAS_DET - 1.0) * 0.06, 0.05, 1)
    nrm = normal_from_height(fold * 0.45 + grime * 0.10 + CANVAS_DET * 0.05, strength=1.0)
    return (save(base, name + "_col"), save(np.repeat(rough[..., None], 3, 2), name + "_rgh"),
            save(downsample(nrm, NRM_TEX), name + "_nrm", jpeg=False))


# ---------------------------------------------------------------- materials
def _bsdf(m):
    m.use_nodes = True
    return m.node_tree.nodes["Principled BSDF"]


def tex_node(m, path, target, noncolor=False):
    b = _bsdf(m); nt = m.node_tree
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path)
    if noncolor: n.image.colorspace_settings.name = 'Non-Color'
    nt.links.new(n.outputs["Color"], _bsdf(m).inputs[target])
    return n


def orm_node(m, path):
    """Wire one ORM image to Roughness (G) + Metallic (B) - the shape the glTF exporter passes through."""
    b = _bsdf(m); nt = m.node_tree
    ni = nt.nodes.new("ShaderNodeTexImage")
    ni.image = bpy.data.images.load(path); ni.image.colorspace_settings.name = 'Non-Color'
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(ni.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], b.inputs["Metallic"])


def paint_mat(name, key, neglected=False, ornament="lined", sign=None, shape=None):
    c, orm, nr = paint_maps(name, KEEPS[key], neglected, ornament, sign, shape)
    m = bpy.data.materials.new(name)
    b = _bsdf(m)
    tex_node(m, c, "Base Color"); orm_node(m, orm)
    nt = m.node_tree
    ni = nt.nodes.new("ShaderNodeTexImage")
    ni.image = bpy.data.images.load(nr); ni.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 1.0
    nt.links.new(ni.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Coat Weight"].default_value = 0.5      # varnish
    b.inputs["Coat Roughness"].default_value = 0.12
    return m


_TXT_CACHE = {}


def _font():
    """Loaded lazily: the scan-source reset (read_factory_settings) wipes datablocks, so a font held
    from before it comes back as a removed StructRNA."""
    for f in bpy.data.fonts:
        if f.filepath == FONT_PATH: return f
    return bpy.data.fonts.load(FONT_PATH)


def text_mask(body, size_m, panel_w, panel_h, res=None):
    # res may be an int (square) or (w, h)
    """Rasterise lettering INTO the texture. Signwriting is paint: it has no relief, and as geometry it
    also cost ~1300 tris per character (Blender tessellates font curves finely).

    Rendered through Blender because there is no PIL here. The text is pre-squashed by the panel's
    aspect: the texture is square but maps onto a panel_w x panel_h face, so anything drawn square in
    UV comes out stretched on the mesh."""
    rw, rh = (res if isinstance(res, tuple) else (res or TEX, res or TEX))
    key = (body, round(size_m, 4), round(panel_w, 3), round(panel_h, 3), rw, rh)
    if key in _TXT_CACHE: return _TXT_CACHE[key]

    prev = bpy.context.window.scene
    sc = bpy.data.scenes.new("txt")
    bpy.context.window.scene = sc
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 1
    sc.render.resolution_x, sc.render.resolution_y = rw, rh
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'Standard'
    wd = bpy.data.worlds.new("txtw"); wd.use_nodes = True
    wd.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)
    sc.world = wd

    bpy.ops.object.text_add()
    t = bpy.context.object
    t.data.body = body
    t.data.font = _font()
    t.data.align_x = 'CENTER'; t.data.align_y = 'CENTER'
    t.data.size = size_m
    m = bpy.data.materials.new("txtm"); m.use_nodes = True
    nt = m.node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1, 1, 1, 1)
    nt.links.new(em.outputs["Emission"], nt.nodes["Material Output"].inputs["Surface"])
    t.data.materials.append(m)
    # Pre-squash to the panel's aspect, THEN correct for a non-square render. The camera fits ortho
    # scale to the WIDER axis, so on a 2048x352 frame the vertical view spans only rh/rw of a UV unit -
    # text scaled for a square frame overflows by rw/rh (~6x here).
    t.scale = (1.0 / panel_w, (1.0 / panel_h) * (rh / rw), 1.0)

    cd = bpy.data.cameras.new("txtc"); cd.type = 'ORTHO'; cd.ortho_scale = 1.0
    cd.sensor_fit = 'HORIZONTAL'                       # pin ortho_scale to X, whatever the aspect
    cam = bpy.data.objects.new("txtc", cd)
    sc.collection.objects.link(cam)
    cam.location = (0, 0, 4)
    sc.camera = cam

    path = os.path.join(TMP, "txt_%s.png" % abs(hash(key)))
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.context.window.scene = prev
    bpy.data.scenes.remove(sc)

    # Mirrored in U: the player is INSIDE the stall. Panels are solidified, so the texture lands on
    # both faces, and u runs counter-clockwise - which reads correctly from outside and back-to-front
    # from in. The inside is the side that matters here, so the lettering is flipped to suit it.
    a = _img_np(bpy.data.images.load(path), None, rw, rh)[:, ::-1, 0]
    _TXT_CACHE[key] = a
    return a


def banner_maps(name, rgb, neglected=False, sign=None):
    """Banners are CLOTH - the same proofed canvas as the roof, not painted timber. Livery colour with
    the gold lining PRINTED on: a banner has no arris to drown in paint, so no moulded bead and no
    wood grain. Runs at TEX; the 2048 albedo existed only to carry the motif, which is gone."""
    h = w = TEX
    v, u = np.mgrid[0:h, 0:w] / float(h)
    gold = np.float32(GOLD)
    col = np.clip(np.float32(rgb)[None, None, :] * (0.88 + 0.12 * CANVAS_DET)[..., None] * PANEL_VALUE, 0, 1)
    metal = np.zeros((h, w), np.float32)
    grime = fbm(h, w, 5, 5)
    rough = np.clip(0.30 + grime * 0.14, 0, 1)

    # Gold lining: ONE thin outer rule and ONE heavier inner. The rules must not be sub-pixel - a 3px
    # hard-edged line falls between mip levels and SHIMMERS at grazing angles, and mipmaps cannot fix
    # that; they average it into the flicker. Both stay >=8px with a soft ramp.
    for inset, wdt in ((0.045, 0.008), (0.080, 0.014)):        # outer thin, inner heavy
        dx = np.minimum(u - inset, (1 - inset) - u)
        dy = np.minimum(v - inset, (1 - inset) - v)
        g = np.clip((np.clip(1 - np.abs(np.minimum(dx, dy)) / wdt, 0, 1) - 0.15) / 0.55, 0, 1)
        col = col * (1 - g[..., None]) + gold * g[..., None]
        metal = metal * (1 - g) + 1.0 * g
        rough = rough * (1 - g) + 0.30 * g

    if sign:                                                   # PRINTED lettering, same ink as the rules
        tm = text_mask(sign, 0.17, 1.46, 0.72)
        g = np.clip((tm - 0.25) / 0.35, 0, 1)
        col = col * (1 - g[..., None]) + gold * g[..., None]
        metal = metal * (1 - g) + 1.0 * g
        rough = rough * (1 - g) + 0.30 * g

    amber = np.array([1.06, 0.94, 0.66], dtype=np.float32)     # varnish veil; worst on the back
    veil = 0.30 if neglected else 0.10
    col = np.clip(col * (1 - veil) + col * amber * veil, 0, 1)

    fold = np.clip(1 - np.abs(((v * 5) % 1.0) - 0.5) * 13, 0, 1)   # hangs in soft folds, like the roof
    col = col * (1 - fold * 0.10)[..., None]
    nrm = normal_from_height(fold * 0.40 + grime * 0.10, strength=0.9)
    orm = np.stack([np.ones_like(rough), np.clip(rough, 0.05, 1.0), np.clip(metal, 0, 1)], -1)
    return (save(col, name + "_col"), save(orm, name + "_orm"),
            save(downsample(nrm, NRM_TEX), name + "_nrm", jpeg=False))


def banner_mat(name, key, neglected=False, sign=None):
    c, orm, nr = banner_maps(name, KEEPS[key], neglected, sign)
    m = bpy.data.materials.new(name); b = _bsdf(m)
    tex_node(m, c, "Base Color"); orm_node(m, orm)
    nt = m.node_tree
    ni = nt.nodes.new("ShaderNodeTexImage")
    ni.image = bpy.data.images.load(nr); ni.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(ni.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Coat Weight"].default_value = 0.45          # the same waterproof proofing as the roof
    b.inputs["Coat Roughness"].default_value = 0.09
    return m


def canvas_mat():
    c, rg, nr = canvas_maps("tilt")
    m = bpy.data.materials.new("tilt")
    b = _bsdf(m)
    tex_node(m, c, "Base Color"); tex_node(m, rg, "Roughness", True)
    nt = m.node_tree
    ni = nt.nodes.new("ShaderNodeTexImage")
    ni.image = bpy.data.images.load(nr); ni.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(ni.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Coat Weight"].default_value = 0.45        # the waterproof proofing, sitting on the cloth
    b.inputs["Coat Roughness"].default_value = 0.09
    return m


_SET_NRM = {}


def _set_nrm_path(st, tag):
    """One normal per PBR SET: it never varies by tint, and each copy is a 2.5MB PNG."""
    if tag not in _SET_NRM:
        _SET_NRM[tag] = save(downsample(st["nrm"], NRM_TEX), "nrm_set_" + tag, jpeg=False)
    return _SET_NRM[tag]


def ground_mat(name):
    """The tober underfoot: a REAL scan of patchy grass worn through to bare earth
    (ambientCG Ground037, CC0). Not a tinted wood scan - there is no such thing as a photo of ground
    in a timber texture, and it showed.

    Grass churned to dirt is the honest fairground: the research is blunt that a fair operates in a
    quagmire, that mud washes off and is NOT cumulative, and that what is permanent is trodden earth.
    A clean lawn would be wrong. Untinted - the scan is already the right colour."""
    d = os.path.join(HERE, "ground_src", "Ground037_2K-JPG_")
    m = bpy.data.materials.new(name); b = _bsdf(m)
    # The scan is a bright DAYLIT ground (mean rgb 0.60/0.58/0.34). This is a night fair lit by
    # near-horizontal stall light, so it has to be knocked well back or it glows.
    col = load_file(d + "Color.jpg", TEX) * GROUND_VALUE
    ao = load_file(d + "AmbientOcclusion.jpg", TEX, True)[:, :, 0]
    # The scan's AO has to be multiplied into the ALBEDO: bake_stall_ao claims the material's
    # occlusion SLOT for the stall's macro shadow, and the exporter's ORM merge keeps that one - so
    # anything left in the ORM's R channel is discarded. This is the crevice detail between clumps.
    col = col * (0.35 + 0.65 * ao)[..., None]
    rgh = load_file(d + "Roughness.jpg", TEX, True)[:, :, 0]
    # The scan's own roughness runs 0.25-0.82 (mean 0.46) - that is a WET-looking floor, near polished
    # plastic at the low end. Trodden earth and dry grass sit ~0.85-0.95, so remap rather than clamp.
    orm = np.stack([ao, np.clip(0.72 + rgh * 0.26, 0, 1), np.zeros_like(rgh)], -1)   # dielectric, matte
    tex_node(m, save(col, name + "_col"), "Base Color")
    orm_node(m, save(orm, name + "_orm"))
    nt = m.node_tree
    ni = nt.nodes.new("ShaderNodeTexImage")
    ni.image = bpy.data.images.load(save(downsample(load_file(d + "NormalGL.jpg", TEX, True), NRM_TEX),
                                         name + "_nrm", jpeg=False))
    ni.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(ni.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def pbr_mat(name, rgb, st=None, rough_lo=0.42, rough_hi=0.45, metal=0.0):
    """A shared PBR set, tinted - real scratches, scuffs, grain, AO and height-reinforced relief.
    Metallic defaults to 0: paint over timber is dielectric, and a grey specular over colour reads as
    pastel. Where the set ships a metalness map (brass), that wins over the flat default."""
    st = st or ROUGH
    m = bpy.data.materials.new(name); b = _bsdf(m)
    col = np.clip(np.float32(rgb)[None, None, :] * st["det"] * st["ao"][..., None], 0, 1)
    met_ch = st["met"] if st["met"] is not None else np.full_like(st["rgh"], metal)
    orm = np.stack([st["ao"], np.clip(rough_lo + st["rgh"] * rough_hi, 0, 1), met_ch], -1)
    tex_node(m, save(col, name + "_col"), "Base Color")
    orm_node(m, save(orm, name + "_orm"))
    nt = m.node_tree
    ni = nt.nodes.new("ShaderNodeTexImage")
    ni.image = bpy.data.images.load(_set_nrm_path(st, "brass" if st is BRASS else "rough"))
    ni.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(ni.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


# The banners wear the SAME livery as the sign board above: maroon with gold lining. The Racinet motif
# is gone - it was only ever a stand-in, since no fairground panel art exists in the public domain, and
# the signwritten board reads more like a real stall than borrowed Greco-Roman scrollwork did.
M_PANEL      = banner_mat("panel", "kingsway_red")
M_PANEL_BACK = banner_mat("panel_back", "kingsway_red", neglected=True)
M_PANEL_SIGN = banner_mat("panel_sign", "kingsway_red", sign="PREMIUM" + chr(10) + "CLUB")
M_TILT, M_TIMBER = canvas_mat(), pbr_mat("timber", TIMBER, ROUGH, 0.55, 0.40)
M_RUST = pbr_mat("fixing", (0.62, 0.34, 0.18), BRASS, 0.30, 0.55)   # galv breached -> rusting steel


def glass_mat():
    """A clear glass orb. It does NOT glow - a uniformly emissive envelope is just a glowing lozenge.
    The amber filament inside is what reads as a bulb, seen through this."""
    m = bpy.data.materials.new("bulb_glass"); b = _bsdf(m)
    b.inputs["Base Color"].default_value = (0.96, 0.94, 0.90, 1)
    b.inputs["Alpha"].default_value = 0.09          # clear glass - you see THROUGH to the filament
    b.inputs["Roughness"].default_value = 0.03
    b.inputs["IOR"].default_value = 1.46
    m.blend_method = 'BLEND'
    return m


def filament_mat():
    """The hot coil: AMBER, tiny, and very bright. 15.0 x lum 0.66 = 9.9, far over the engine's 1.6
    glow threshold. Clipping is fine HERE precisely because the source is tiny - a blown-out filament
    seen through clear glass is what a lit bulb looks like. It was the whole ENVELOPE glowing that
    read as a white blob, not brightness itself."""
    m = bpy.data.materials.new("bulb_filament"); b = _bsdf(m)
    b.inputs["Base Color"].default_value = (1.0, 0.72, 0.34, 1)
    b.inputs["Emission Color"].default_value = (1.0, 0.62, 0.22, 1)   # amber
    b.inputs["Emission Strength"].default_value = 15.0
    b.inputs["Roughness"].default_value = 0.4
    return m


M_GLASS, M_FIL = glass_mat(), filament_mat()


# Even internal parts were painted - bare timber anywhere reads as unfinished. The lampboard is the
# most-repainted element on the stall, so it gets the freshest paint and throws the cabochons back.
M_BOARD = paint_mat("lampboard", "kingsway_red", ornament="lined", sign=SIGN, shape=(2048, 352))
M_LEG   = paint_mat("leg", "empire_blue", ornament="none")
M_GOLD  = pbr_mat("goldleaf", GOLD, BRASS, 0.16, 0.30, 1.0)   # brass casting: the finial
GROUND_VALUE = 0.42                    # night fair: the scan is daylit and far too bright raw
M_GROUND = ground_mat("ground")        # real scan: patchy grass worn to earth


# ---------------------------------------------------------------- geometry helpers
def ang(i):   return 2 * math.pi * i / SIDES
def corner(i, r=None, z=0.0):
    r = R if r is None else r
    return Vector((r * math.cos(ang(i)), r * math.sin(ang(i)), z))


def norm(bm):
    """Face winding is not reliable across the builders below; solidify + shading both need it right."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def obj_from(bm, name, mat, smooth=False):
    norm(bm)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    if smooth:
        bpy.context.view_layer.objects.active = o; o.select_set(True)
        bpy.ops.object.shade_smooth(); o.select_set(False)
    return o


def bowed_panel(bm, i, z0, z1, bow, flip_uv=False):
    """One convex shutter: chord between corners i..i+1, bowed outward. UV: u along chord, v up."""
    uvl = bm.loops.layers.uv.verify()
    a, b = corner(i), corner(i + 1)
    seg = 10
    grid = []
    for s in range(seg + 1):
        t = s / seg
        p = a.lerp(b, t)
        n = Vector((math.cos(ang(i) + math.pi / SIDES), math.sin(ang(i) + math.pi / SIDES), 0))
        p = p + n * (bow * math.sin(math.pi * t))          # convex bow
        grid.append([bm.verts.new((p.x, p.y, z0)), bm.verts.new((p.x, p.y, z1))])
    for s in range(seg):
        f = bm.faces.new([grid[s][0], grid[s + 1][0], grid[s + 1][1], grid[s][1]])
        u0, u1 = s / seg, (s + 1) / seg
        if flip_uv: u0, u1 = 1 - u0, 1 - u1
        for lp, uv in zip(f.loops, [(u0, 0), (u1, 0), (u1, 1), (u0, 1)]):
            lp[uvl].uv = uv


def box(bm, p0, p1, w, h):
    p0, p1 = Vector(p0), Vector(p1); d = p1 - p0
    dn = d.normalized()
    side = dn.cross(Vector((0, 0, 1)))
    side = (side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))) * w / 2
    vert = side.cross(dn).normalized() * h / 2
    pts = [p0 + side * a + vert * b for a in (1, -1) for b in (1, -1)] + \
          [p1 + side * a + vert * b for a in (1, -1) for b in (1, -1)]
    vs = [bm.verts.new(p) for p in pts]
    for f in [(0, 1, 3, 2), (4, 6, 7, 5), (0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6)]:
        try: bm.faces.new([vs[i] for i in f])
        except ValueError: pass


# ---------------------------------------------------------------- the shutter ring (the structure)
# Each shutter is its own object so it can carry its own livery colour + front/back paint age.
for i in range(SIDES):
    back = (math.cos(ang(i) + math.pi / SIDES) < -0.3)     # far side = oldest paint, never repainted
    mat = M_PANEL_SIGN if i % 2 == 0 else (M_PANEL_BACK if back else M_PANEL)
    bm = bmesh.new()
    # Flat BANNERS between the pillars, in the same livery as the sign board above. Not the researched
    # convex shutter: a banner is stretched flat between its posts, so no bow by design.
    bowed_panel(bm, i, COUNTER_H - SKIRT_H, COUNTER_H, 0.0)
    norm(bm)
    bmesh.ops.solidify(bm, geom=bm.faces[:] + bm.verts[:] + bm.edges[:], thickness=-0.012)
    obj_from(bm, f"Banner{i}", mat)


# legs: light section, ground to eaves. Ground clearance = the stall stands on packing, clear of the mud.
bm = bmesh.new()
for i in range(SIDES):
    p = corner(i)
    box(bm, (p.x, p.y, 0.0), (p.x, p.y, EAVES_H), POST, POST)
for i in range(SIDES):                                   # eaves beam ring, capping the pillars
    box(bm, corner(i, R, EAVES_H), corner(i + 1, R, EAVES_H), BEAM_W, BEAM_H)
obj_from(bm, "Legs", M_LEG)

# ---------------------------------------------------------------- roof: canvas tilt over a rafter frame
bm = bmesh.new()
HUB = 0.16
for i in range(SIDES):                                   # rafters, eaves -> crown hub (exposed from below)
    e = corner(i, R + OVERHANG, EAVES_H - 0.02)
    box(bm, e, (HUB * math.cos(ang(i)), HUB * math.sin(ang(i)), APEX_H - 0.10), 0.055, 0.085)
obj_from(bm, "Rafters", M_TIMBER)

# Tilt: a grid PER BAY with shared verts, so it shades smoothly and can actually sag. Bays stay
# unwelded from each other - the canvas creases over each rafter, which is what a real tent does.
bm = bmesh.new(); uvl = bm.loops.layers.uv.verify()
rings, across = 8, 6
TMAX = 1.0 - HUB / (R + OVERHANG)          # stop where the crown hub starts
apex = Vector((0, 0, APEX_H))
for i in range(SIDES):
    e0, e1 = corner(i, R + OVERHANG, EAVES_H), corner(i + 1, R + OVERHANG, EAVES_H)
    grid = []
    for a in range(across + 1):
        s = a / across
        e = e0.lerp(e1, s)
        colv = []
        for j in range(rings + 1):
            t = TMAX * j / rings
            p = e.lerp(apex, t)
            sag = 0.055 * math.sin(math.pi * s) * (1 - t)   # pulled to the rafters, dips mid-bay
            colv.append(bm.verts.new((p.x, p.y, p.z - sag)))
        grid.append(colv)
    for a in range(across):
        for j in range(rings):
            f = bm.faces.new([grid[a][j], grid[a + 1][j], grid[a + 1][j + 1], grid[a][j + 1]])
            u0, u1 = a / across, (a + 1) / across
            v0, v1 = j / rings, (j + 1) / rings
            for lp, uv in zip(f.loops, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
                lp[uvl].uv = uv
norm(bm)
bmesh.ops.solidify(bm, geom=bm.faces[:] + bm.verts[:] + bm.edges[:], thickness=-0.008)
obj_from(bm, "Tilt", M_TILT, smooth=True)

# crown: caps the hole the tilt leaves at the hub
bm = bmesh.new()
revolve = [bm.verts.new((HUB * math.cos(ang(i) + math.pi / SIDES),
                         HUB * math.sin(ang(i) + math.pi / SIDES), APEX_H - 0.10)) for i in range(SIDES)]
bm.faces.new(revolve)
obj_from(bm, "Crown", M_TIMBER)

# ---------------------------------------------------------------- lampboard + cabochons (the whole point)
bm = bmesh.new(); uvl = bm.loops.layers.uv.verify()
for i in range(SIDES):
    a, b = corner(i, BULB_R, EAVES_H), corner(i + 1, BULB_R, EAVES_H)
    f = bm.faces.new([bm.verts.new(p) for p in
                      (a, b, Vector((b.x, b.y, EAVES_H - FASCIA_H)), Vector((a.x, a.y, EAVES_H - FASCIA_H)))])
    for lp, uv in zip(f.loops, [(0, 1), (1, 1), (1, 0), (0, 0)]): lp[uvl].uv = uv
norm(bm)
bmesh.ops.solidify(bm, geom=bm.faces[:] + bm.verts[:] + bm.edges[:], thickness=-0.010)   # 10mm board
obj_from(bm, "Lampboard", M_BOARD)


# cabochons: face-drilled through the board at 80mm centres, one row outside + one row facing IN over
# the counter (interior lighting is unsourced - inferred, but the camera sits under it).
def make_lamp():
    """A glass orb with an amber emissive filament inside. Built ONCE; every lamp instances this single
    mesh, so the GLB stores one mesh and ~310 nodes.

    Modelled rather than sourced: no CC0 fairground cabochon exists, and the CC0 bulb that does is a
    whole incandescent - cap, wires, coil - at 4372 tris, of which only the orb and a hint of filament
    survive being seen at 45mm across a dark stall. This is ~200 tris and says the same thing."""
    r = CAB_D / 2
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r)
    n_orb = len(bm.faces)

    # Filament: a ROUND amber core, not a 4mm sliver. A sliver only reads as lit via bloom - and glow
    # is tier-gated (Medium+), so on Low the bulb would be a dead glass bead. A core this size glows on
    # its own at any tier, and blooms into a halo where glow IS on.
    tmp = bmesh.new()
    bmesh.ops.create_icosphere(tmp, subdivisions=1, radius=r * 0.46)
    tme = bpy.data.meshes.new("_fil"); tmp.to_mesh(tme); tmp.free()
    bm.from_mesh(tme); bpy.data.meshes.remove(tme)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new("Lamp")
    bm.to_mesh(me); bm.free()
    me.materials.append(M_GLASS)     # slot 0: the orb
    me.materials.append(M_FIL)       # slot 1: the filament
    for i, poly in enumerate(me.polygons):
        poly.material_index = 0 if i < n_orb else 1
        poly.use_smooth = i < n_orb                    # orb smooth; the coil is a hard little shape
    return me


LAMP_K = (1.0, 0.72, 0.42)          # 2700K
CAB_ME = make_lamp()
UP = Vector((0, 0, 1))
nb = 0


def place_cab(pos, facing, own_light=0.0):
    """Instance the shared lamp mesh, oriented along `facing`.

    own_light > 0 puts a real point light INSIDE this bulb's orb, so it is genuinely a lit bulb rather
    than one lit by a neighbour a few centimetres away. Shadowless and short-range: Godot's clustered
    renderer takes many of those cheaply - it is shadow MAPS that don't scale."""
    global nb
    o = bpy.data.objects.new(f"Lamp{nb}", CAB_ME)                # SHARED mesh data -> real instancing
    o.location = pos
    o.rotation_euler = UP.rotation_difference(facing.normalized()).to_euler()
    bpy.context.collection.objects.link(o)
    if own_light > 0.0:
        ld = bpy.data.lights.new(f"Fil{nb}", 'POINT')
        ld.energy = own_light
        ld.color = LAMP_K
        ld.shadow_soft_size = CAB_D * 0.5
        ld.use_custom_distance = True
        ld.cutoff_distance = 1.1                                 # short range keeps clusters cheap
        lo = bpy.data.objects.new(f"Fil{nb}", ld)
        lo.location = pos + facing.normalized() * (CAB_D * 0.5)  # at the filament, inside the orb
        bpy.context.collection.objects.link(lo)
    nb += 1


# The bulb ring is mounted on the eaves BEAM RING that caps the pillars (radius R) - specifically its
# INSIDE face, firing inward over the counter. Not on the lampboard: that sits out at BULB_R, past the
# pillars and clear of the beam entirely.
LAMP_W    = 0.060                       # the bulb's envelope diameter
LAMP_PITCH = max(CAB_PITCH, LAMP_W + 0.045)   # centres: 80mm is the CABOCHON spec; a bulb needs clearance
JOIN_CLEAR = POST / 2 + LAMP_W / 2 + 0.02     # keep clear of the pillar at each join
for i in range(SIDES):
    a, b = corner(i, R, 0), corner(i + 1, R, 0)
    # The face normal of a decagon bay is at ang(i)+pi/SIDES, NOT the radial direction of the point:
    # using the radial direction tilts every lamp that isn't at the chord's midpoint.
    face_n = Vector((math.cos(ang(i) + math.pi / SIDES), math.sin(ang(i) + math.pi / SIDES), 0))
    chord = (b - a).length
    usable = chord - 2 * JOIN_CLEAR
    n = max(1, int(usable / LAMP_PITCH))
    for j in range(n + 1):
        t = (JOIN_CLEAR + j * usable / n) / chord
        p = a.lerp(b, t)
        seat = Vector((p.x, p.y, EAVES_H)) - face_n * (BEAM_W / 2)   # ON the beam's inside face
        place_cab(seat, -face_n, own_light=0.9)                      # its OWN light, in its own orb
# Interior lamps under each rafter. INFERRED - the record is silent on stall interiors - but the player
# sits under this roof, and an unlit tilt reads as a dark tent rather than a lit stall.
for i in range(SIDES):
    e = corner(i, R + OVERHANG, EAVES_H - 0.02)
    hub = Vector((HUB * math.cos(ang(i)), HUB * math.sin(ang(i)), APEX_H - 0.10))
    steps = max(2, int((hub - e).length / max(0.16, LAMP_PITCH)))
    for j in range(1, steps):
        p = e.lerp(hub, j / steps)
        z = p.z - 0.043
        # The rafter runs OUT to the eaves at BULB_R and DIPS below the beam ring on the way. No lamp
        # goes on that stretch: outboard of the top rail it hangs below the frame, over the opening
        # rather than under the roof. Only the inboard run - above the rail AND inside it - is lit.
        if z < EAVES_H or math.hypot(p.x, p.y) > R: continue
        place_cab(Vector((p.x, p.y, z)), Vector((0, 0, -1)))             # seated under the rafter

# scalloped valance: hangs under the lampboard. Reads as fairground from any distance, at any angle.
bm = bmesh.new(); uvl = bm.loops.layers.uv.verify()
VAL_H, SCALLOPS = 0.24, 4
z_top = EAVES_H - FASCIA_H
for i in range(SIDES):
    a, b = corner(i, BULB_R, 0), corner(i + 1, BULB_R, 0)
    steps = SCALLOPS * 8
    prev = None
    for s in range(steps + 1):
        t = s / steps
        p = a.lerp(b, t)
        # scalloped hem: a run of semicircular dags, the classic valance edge
        ph = (t * SCALLOPS) % 1.0
        dip = math.sqrt(max(0.0, 1.0 - (2 * ph - 1) ** 2))
        z_bot = z_top - VAL_H * (0.30 + 0.70 * dip)
        cur = (bm.verts.new((p.x, p.y, z_top)), bm.verts.new((p.x, p.y, z_bot)))
        if prev:
            f = bm.faces.new([prev[0], cur[0], cur[1], prev[1]])
            # same per-bay u as the tilt, so the stripes run continuously from canopy to hem; v is
            # scaled to the hem's real drop so the creases keep the canopy's pitch instead of bunching
            u0, u1 = (s - 1) / steps, s / steps
            vh = VAL_H / 2.0
            for lp, uv in zip(f.loops, [(u0, vh), (u1, vh), (u1, 0), (u0, 0)]): lp[uvl].uv = uv
        prev = cur
norm(bm)
bmesh.ops.solidify(bm, geom=bm.faces[:] + bm.verts[:] + bm.edges[:], thickness=-0.008)
obj_from(bm, "Valance", M_TILT)

# turned finial at the apex
bm = bmesh.new()
FIN = [(0.0, 0.0), (0.05, 0.03), (0.075, 0.09), (0.035, 0.15), (0.06, 0.21), (0.022, 0.32), (0.0, 0.42)]
seg = 16
vs = []
for i in range(seg):
    aa = 2 * math.pi * i / seg
    for (r, z) in FIN:
        vs.append(bm.verts.new((r * math.cos(aa), r * math.sin(aa), APEX_H - 0.12 + z)))
n = len(FIN)
for i in range(seg):
    i2 = (i + 1) % seg
    for j in range(n - 1):
        try: bm.faces.new([vs[i * n + j], vs[i2 * n + j], vs[i2 * n + j + 1], vs[i * n + j + 1]])
        except ValueError: pass
obj_from(bm, "Finial", M_GOLD, smooth=True)

# ---------------------------------------------------------------- the ground it stands on
# The stall carries its own tober. Extends past the eaves so it fills the view under the banners; UVs
# are world-scaled (metres / GROUND_TILE) so the scan repeats rather than stretching across 6m.
GROUND_R, GROUND_TILE = BULB_R + 1.4, 2.0    # the scan photographs ~2m of ground: tile at its real size
GROUND_DISP, GROUND_GRID = 0.035, 110        # 35mm of relief; grid cells across the diameter

# DISPLACED ground. glTF has no height/parallax slot and Godot's heightmap doesn't survive the import,
# so relief has to be real geometry: a grid displaced by the scan's own Displacement map. 35mm is the
# scale of trodden earth - ruts and clumps, not dunes. Tapered to flat at the rim so the silhouette
# doesn't break against the backdrop, and under the stall's own footprint so the legs still seat.
_disp = load_file(os.path.join(HERE, "ground_src", "Ground037_2K-JPG_Displacement.jpg"), 512, True)[:, :, 0]
_dn = _disp.shape[0]


def _ground_z(x, y):
    uu = int(((x / GROUND_TILE) % 1.0) * (_dn - 1))
    vv = int(((y / GROUND_TILE) % 1.0) * (_dn - 1))
    r = math.hypot(x, y)
    edge = min(1.0, max(0.0, (GROUND_R - r) / 1.2))           # flat at the rim
    seat = min(1.0, max(0.0, (r - (R - 0.35)) / 0.5))         # flat under the stall's footprint
    return (_disp[vv, uu] - 0.5) * 2.0 * GROUND_DISP * edge * seat


bm = bmesh.new(); uvl = bm.loops.layers.uv.verify()
step = (2 * GROUND_R) / GROUND_GRID
grid = {}
for iy in range(GROUND_GRID + 1):
    for ix in range(GROUND_GRID + 1):
        x = -GROUND_R + ix * step
        y = -GROUND_R + iy * step
        if math.hypot(x, y) > GROUND_R: continue
        grid[(ix, iy)] = bm.verts.new((x, y, 0.004 + _ground_z(x, y)))
for iy in range(GROUND_GRID):
    for ix in range(GROUND_GRID):
        q = [grid.get((ix, iy)), grid.get((ix + 1, iy)), grid.get((ix + 1, iy + 1)), grid.get((ix, iy + 1))]
        if any(v is None for v in q): continue
        f = bm.faces.new(q)
        for lp in f.loops:
            co = lp.vert.co
            lp[uvl].uv = (co.x / GROUND_TILE, co.y / GROUND_TILE)
obj_from(bm, "Ground", M_GROUND, smooth=True)

# ---------------------------------------------------------------- fixings: rust only where galv is breached
bm = bmesh.new()
for i in range(SIDES):
    p = corner(i)
    for z in (COUNTER_H - SKIRT_H + 0.06, COUNTER_H - 0.10):
        o = Vector((p.x, p.y, 0)).normalized()
        box(bm, Vector((p.x, p.y, z)) + o * 0.01, Vector((p.x, p.y, z)) + o * 0.05, 0.022, 0.022)
obj_from(bm, "Fixings", M_RUST)

# ---------------------------------------------------------------- the ring actually emits light
# An emissive material in Godot GLOWS but lights nothing: it is a bright surface, not a lamp. Without
# these the interior is lit only by the scene rig and the bulbs read as white blobs stuck on a dark
# stall. One lamp per bay rather than one per bulb - 310 point lights is not affordable, and at this
# radius a single warm source per bay is indistinguishable from its 13 bulbs.
_nlamp = 0


def point_lamp(pos, energy):
    """A real point light. Godot Forward+ is clustered, so shadowless point lights are cheap - but not
    310 of them. One per few bulbs is indistinguishable at this radius and affordable."""
    global _nlamp
    ld = bpy.data.lights.new(f"Lamp{_nlamp}", 'POINT')
    ld.energy = energy
    ld.color = LAMP_K
    ld.shadow_soft_size = 0.06
    lo = bpy.data.objects.new(f"BayLamp{_nlamp}", ld)
    lo.location = pos
    bpy.context.collection.objects.link(lo)
    _nlamp += 1


# The wall ring needs no shared lamps: every ring bulb carries its own light (place_cab own_light).

# The rafter banks. These had NO lights at all - 180 of the 310 bulbs were pure decoration, glowing
# but lighting nothing, which is exactly why the roof stayed dark above the ring.
for i in range(SIDES):
    e = corner(i, R + OVERHANG, EAVES_H - 0.02)
    hub = Vector((HUB * math.cos(ang(i)), HUB * math.sin(ang(i)), APEX_H - 0.10))
    for t in (0.22, 0.50, 0.78):
        p = e.lerp(hub, t)
        if p.z - 0.05 < EAVES_H: continue          # nothing below the beam
        point_lamp(Vector((p.x, p.y, p.z - 0.05)), 6.0)

# ---------------------------------------------------------------- baked ambient occlusion
# The engine's SSAO is tuned to the BOARD: SsaoRadius is 1.1cm, tightened deliberately so the seam
# between touching coins reads. A 30cm counter overhang shadowing the wall beneath it is metre-scale -
# ~30x outside that radius - so screen-space AO can never produce it, and widening the radius per
# flavour would wreck the coin AO in the same scene. For a static prop the occlusion has to be BAKED.
#
# One bake serves every shutter: the stall is rotationally symmetric, so each bay's occlusion is
# identical, and each shutter maps its own 0..1 UV. Baked into the glTF OCCLUSION slot (via the
# exporter's "glTF Material Output" group), so it multiplies ambient only - not albedo.
def gltf_occlusion_group():
    name = "glTF Material Output"
    g = bpy.data.node_groups.get(name)
    if g: return g
    g = bpy.data.node_groups.new(name, "ShaderNodeTree")
    g.interface.new_socket(name="Occlusion", in_out='INPUT', socket_type='NodeSocketFloat')
    g.nodes.new("NodeGroupInput")
    return g


def bake_stall_ao(res=512, samples=48):
    """Bake ambient occlusion into a SECOND UV set and feed the glTF occlusion slot.

    Why baked, not SSAO: the engine's SsaoRadius is 1.1cm, tuned so the seam between touching coins
    reads on the board. The counter overhangs its wall by ~280mm - roughly 25x that radius - so
    screen-space AO cannot produce that shadow, and widening the radius per flavour would wreck the
    coin AO in the same scene. A static prop should carry its occlusion anyway.

    Why a second UV set: the shutters are bowed_panel + solidify, so inner and outer faces SHARE UV0.
    Baking there lets the unoccluded outer face overwrite the occluded inner face and the shadow
    vanishes. UVAO is packed non-overlapping across every object, so each gets its own atlas region -
    materials can still be shared between bays, exactly as a lightmap works.

    The lamps are excluded: 310 of them share one mesh, and instancing is incompatible with per-object
    atlas regions. They are emissive; they have nothing to gain."""
    targets = [o for o in bpy.data.objects if o.type == 'MESH' and o.data is not CAB_ME]
    if not targets: return
    for o in targets:
        if "UVAO" not in o.data.uv_layers:
            o.data.uv_layers.new(name="UVAO")
        o.data.uv_layers["UVAO"].active = True
    for x in bpy.data.objects: x.select_set(False)
    for o in targets: o.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004)
    bpy.ops.object.mode_set(mode='OBJECT')

    img = bpy.data.images.new("ao_stall", res, res, alpha=False)
    mats = []
    for o in targets:
        for m in o.data.materials:
            if m and m not in mats: mats.append(m)
    tmp_nodes = []
    for m in mats:
        n = m.node_tree.nodes.new("ShaderNodeTexImage"); n.image = img
        m.node_tree.nodes.active = n
        tmp_nodes.append((m, n))

    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = samples
    sc.render.bake.margin = 6
    sc.render.bake.use_pass_direct = False
    sc.render.bake.use_pass_indirect = False
    bpy.ops.object.bake(type='AO', use_clear=True)
    for m, n in tmp_nodes: m.node_tree.nodes.remove(n)

    path = os.path.join(TMP, "ao_stall.png")
    img.filepath_raw = path; img.file_format = 'PNG'; img.save()
    ao = bpy.data.images.load(path); ao.colorspace_settings.name = 'Non-Color'
    for m in mats:
        nt = m.node_tree
        uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "UVAO"
        ni = nt.nodes.new("ShaderNodeTexImage"); ni.image = ao
        nt.links.new(uvn.outputs["UV"], ni.inputs["Vector"])
        grp = nt.nodes.new("ShaderNodeGroup"); grp.node_tree = gltf_occlusion_group()
        nt.links.new(ni.outputs["Color"], grp.inputs["Occlusion"])
    for o in targets:                       # UV0 stays the render/albedo set
        o.data.uv_layers[0].active = True
        o.select_set(False)
    Carrom_ao = np.asarray(img.pixels[:]).reshape(res, res, 4)[:, :, 0]
    print(f"[stall] baked AO: min {Carrom_ao.min():.3f} mean {Carrom_ao.mean():.3f} "
          f"| occluded texels (<0.75): {100.0 * (Carrom_ao < 0.75).mean():.1f}%")


bake_stall_ao()

# ---------------------------------------------------------------- export
for o in bpy.data.objects:
    o.select_set(False)
# The scan GLBs (coin, table) are imported ONLY to read their embedded textures; their meshes are
# discarded immediately after. If that discard is ever lost, they export INSIDE this prop - which has
# happened, silently, costing 25MB and 14k faces. This stall builds nothing but a stall: assert it.
_EXPECTED = ("Banner", "Legs", "Rafters", "Tilt", "Crown", "Valance", "Lampboard", "Ground",
             "Signwriting", "Finial", "Fixings", "Lamp", "BayLamp", "Fil")
_strays = [o.name for o in bpy.data.objects
           if o.type == 'MESH' and not any(o.name.startswith(e) for e in _EXPECTED)]
if _strays:
    raise RuntimeError("build_stall: NON-STALL geometry would be exported: %s" % _strays[:8])
print(f"[stall] guard: {len([o for o in bpy.data.objects if o.type == 'MESH'])} meshes, all stall parts")

bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_yup=True, use_selection=False,
                          export_lights=True)   # the bulb ring is the stall's lighting
tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
print(f"[stall] {SIDES}-sided round stall -> {OUT}")
print(f"[stall] across-flats {ACROSS_FLATS}m  apex {APEX_H}m  counter {COUNTER_H}m  "
      f"{nb} cabochons @ {CAB_PITCH*1000:.0f}mm  ~{tris} faces")
