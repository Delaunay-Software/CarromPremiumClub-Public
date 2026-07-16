"""Render the stall GLB EXACTLY as authored — no material substitution, so what you see is what the
engine shows once the manifest's `material` override is dropped. Night-fair lighting to match backdrop.

  blender -b --python preview_stall.py -- <glb> <out.png> [view]

view: 'hero' (default, 3/4 exterior) | 'seat' (player's eye at the counter) | 'both' (writes _hero/_seat)
"""
import bpy, sys, math, mathutils, os

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, PNG = argv[0], argv[1]
VIEW = argv[2] if len(argv) > 2 else "hero"
HDR = "C:/Users/User/Documents/GitHub/HDRI/outputs/FUNHOUSE_dim.hdr"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

# Night-fair world: dim HDRI only. The stall must read by its OWN emissive bulbs — if it only
# looks right under a fill sun, it will not look right in game.
w = bpy.data.worlds.new("w"); bpy.context.scene.world = w; w.use_nodes = True
nt = w.node_tree
env = nt.nodes.new("ShaderNodeTexEnvironment")
if os.path.exists(HDR):
    env.image = bpy.data.images.load(HDR)
    nt.links.new(env.outputs["Color"], nt.nodes["Background"].inputs["Color"])
nt.nodes["Background"].inputs[1].default_value = 0.35   # dim — night

meshes = [o for o in bpy.data.objects if o.type == 'MESH']
mn = [1e9] * 3; mx = [-1e9] * 3
for o in meshes:
    for c in o.bound_box:
        p = o.matrix_world @ mathutils.Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], p[i]); mx[i] = max(mx[i], p[i])
ctr = mathutils.Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
rad = max(mx[i] - mn[i] for i in range(3))

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
try: sc.cycles.device = 'GPU'
except Exception: pass
sc.cycles.samples = 180
sc.render.resolution_x, sc.render.resolution_y = 1100, 1000
sc.view_settings.view_transform = 'AgX'

cam_d = bpy.data.cameras.new("c"); cam_d.lens = 48
# Godot's Camera3D.Fov is VERTICAL (KeepAspect defaults to KEEP_HEIGHT). Blender fits the sensor to the
# LARGER dimension by default, which on a landscape render silently narrows the vertical FOV - i.e. the
# preview would judge the stall through a tighter lens than the game actually uses. Pin it vertical.
cam_d.sensor_fit = 'VERTICAL'
cam_d.sensor_height = 36.0
cam = bpy.data.objects.new("c", cam_d); bpy.context.collection.objects.link(cam)
sc.camera = cam


def shoot(loc, aim, lens, path):
    cam_d.lens = lens
    cam.location = loc
    cam.rotation_euler = (aim - loc).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[preview]", path)


def hero(path):
    shoot(ctr + mathutils.Vector((rad * 1.15, -rad * 1.45, rad * 0.25)),
          ctr + mathutils.Vector((0, 0, -rad * 0.05)), 48, path)


# The REAL game camera (CameraOrbit / CameraConfig): Fov 55 (=34.6mm on a 36mm sensor), orbits the
# board centre at 25-105cm, elevation 10-35 deg. The board plane is the stall's counter height, so
# everything here is expressed relative to COUNTER_Z.
COUNTER_Z = 0.85
GAME_FOV_LENS = 34.6


def game(path, dist_cm, elev_deg):
    """Mirrors CameraOrbit.UpdateCameraPosition exactly, including the sky-pitch trick: below
    MinOrbitElevation (10 deg) the camera stops descending and instead raises the LookAt target,
    so the player pitches their head UP at the stall. Elevation clamps to MinElevation = -80."""
    d = dist_cm / 100.0
    orbit_elev = max(elev_deg, 10.0)                 # MinOrbitElevation
    sky_pitch = max(0.0, 10.0 - elev_deg)
    e = math.radians(orbit_elev)
    eye = mathutils.Vector((0.0, -d * math.cos(e), COUNTER_Z + d * math.sin(e)))
    tgt = mathutils.Vector((0.0, 0.0, COUNTER_Z + math.tan(math.radians(sky_pitch)) * d))
    shoot(eye, tgt, GAME_FOV_LENS, path)


def seat(path):
    # Default gameplay framing: 60cm out, 35 deg elevation.
    game(path, 60, 35)


if VIEW == "both":
    stem = PNG[:-4] if PNG.lower().endswith(".png") else PNG
    hero(stem + "_hero.png"); seat(stem + "_seat.png")
elif VIEW == "game":
    # the actual zoom/elevation envelope the player can reach
    stem = PNG[:-4] if PNG.lower().endswith(".png") else PNG
    game(stem + "_default.png", 60, 35)      # default framing
    game(stem + "_wide.png", 105, 10)        # zoomed out, level
    game(stem + "_lookup.png", 85, -35)      # leaning back, head pitched up at the stall
elif VIEW == "seat":
    seat(PNG)
else:
    hero(PNG)
