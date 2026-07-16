"""Faithful preview: import GLB, keep ALL authored materials, light with the FUNHOUSE HDRI.
  blender -b --python preview_asis.py -- <glb> <png> [camZ_frac]"""
import bpy, sys, math, mathutils
argv = sys.argv[sys.argv.index("--") + 1:]
GLB, PNG = argv[0], argv[1]
HDR = "C:/Users/User/Documents/GitHub/HDRI/outputs/FUNHOUSE_dim.hdr"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

w = bpy.data.worlds.new("w"); bpy.context.scene.world = w; w.use_nodes = True
nt = w.node_tree; bg = nt.nodes["Background"]
env = nt.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDR)
nt.links.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs[1].default_value = 1.1

mn = [1e9]*3; mx = [-1e9]*3
for o in [o for o in bpy.data.objects if o.type == 'MESH']:
    for c in o.bound_box:
        p = o.matrix_world @ mathutils.Vector(c)
        for i in range(3): mn[i] = min(mn[i], p[i]); mx[i] = max(mx[i], p[i])
ctr = mathutils.Vector(((mn[0]+mx[0])/2, (mn[1]+mx[1])/2, (mn[2]+mx[2])/2)); rad = max(mx[i]-mn[i] for i in range(3))
cam_d = bpy.data.cameras.new("c"); cam_d.lens = 52
cam = bpy.data.objects.new("c", cam_d); bpy.context.collection.objects.link(cam)
aim = ctr + mathutils.Vector((0, 0, -rad*0.16))
cam.location = ctr + mathutils.Vector((rad*0.95, -rad*1.15, rad*0.02))   # low angle to see feet + ground
cam.rotation_euler = (aim - cam.location).to_track_quat('-Z','Y').to_euler(); bpy.context.scene.camera = cam
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); bpy.context.collection.objects.link(sun)
sun.data.energy = 2.2; sun.data.angle = math.radians(2.5); sun.rotation_euler = (math.radians(52), 0, math.radians(40))

sc = bpy.context.scene; sc.render.engine = 'CYCLES'
try: sc.cycles.device = 'GPU'
except Exception: pass
sc.cycles.samples = 160; sc.render.resolution_x = 1100; sc.render.resolution_y = 950
sc.view_settings.view_transform = 'AgX'
sc.render.filepath = PNG; bpy.ops.render.render(write_still=True)
print("[preview]", PNG)
