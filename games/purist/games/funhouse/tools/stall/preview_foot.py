"""Tight close-up on the front post base to check the metal feet + grass.
  blender -b --python preview_foot.py -- <glb> <png>"""
import bpy, sys, math, mathutils
argv = sys.argv[sys.argv.index("--") + 1:]; GLB, PNG = argv[0], argv[1]
HDR = "C:/Users/User/Documents/GitHub/HDRI/outputs/FUNHOUSE_dim.hdr"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
w = bpy.data.worlds.new("w"); bpy.context.scene.world = w; w.use_nodes = True
nt = w.node_tree; env = nt.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDR)
nt.links.new(env.outputs["Color"], nt.nodes["Background"].inputs["Color"]); nt.nodes["Background"].inputs[1].default_value = 1.1
# nearest foot to the camera side (front, -Y): the (0.73,-2.25) post
target = mathutils.Vector((0.73, -2.25, 0.12))
cam_d = bpy.data.cameras.new("c"); cam_d.lens = 70
cam = bpy.data.objects.new("c", cam_d); bpy.context.collection.objects.link(cam)
cam.location = target + mathutils.Vector((0.55, -0.95, 0.42))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z','Y').to_euler(); bpy.context.scene.camera = cam
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); bpy.context.collection.objects.link(sun)
sun.data.energy = 2.4; sun.data.angle = math.radians(2.5); sun.rotation_euler = (math.radians(50), 0, math.radians(35))
sc = bpy.context.scene; sc.render.engine = 'CYCLES'
try: sc.cycles.device = 'GPU'
except Exception: pass
sc.cycles.samples = 180; sc.render.resolution_x = 1000; sc.render.resolution_y = 1000
sc.view_settings.view_transform = 'AgX'
sc.render.filepath = PNG; bpy.ops.render.render(write_still=True); print("[foot]", PNG)
