"""NON-DESTRUCTIVE add-ons to the CURRENT funfair_stall.glb:
  1. cast-iron FOOT PLATES where each Leg upright meets the ground (bolted base + collar);
  2. real geometric DISPLACEMENT on the flat Ground mesh, driven by its own grass colour.
Deletes nothing — imports the current GLB, adds two meshes / one baked modifier, re-exports in place.

  blender --background --python stall_addons.py -- <inout.glb>
"""
import bpy, sys, math, bmesh
from mathutils import Vector

GLB = sys.argv[sys.argv.index("--") + 1:][0]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
for o in bpy.data.objects: o.select_set(False)   # glTF import leaves all selected

# ---- detect the leg feet: cluster the lowest vertex band of `Legs` into upright XY centres ----
legs = bpy.data.objects.get("Legs")
vs = [legs.matrix_world @ v.co for v in legs.data.vertices]
zmin = min(p.z for p in vs)
foot_sz = 0.06                                    # measured 6 cm square posts
clusters = []
for p in [q for q in vs if q.z < zmin + 0.05]:
    for c in clusters:
        if math.hypot(p.x - c[0], p.y - c[1]) < 0.3:
            n = c[2]; c[0] = (c[0]*n + p.x)/(n+1); c[1] = (c[1]*n + p.y)/(n+1); c[2] = n+1; break
    else:
        clusters.append([p.x, p.y, 1])
print(f"[addons] {len(clusters)} leg feet at z={zmin:.3f}")

# ---- cast-iron foot plate (plate + tapered collar the post seats into + 4 corner bolts) ----
fbm = bmesh.new()
def box(cx, cy, cz, sx, sy, sz):
    t = bmesh.new(); bmesh.ops.create_cube(t, size=1.0)
    for v in t.verts: v.co = Vector((v.co.x*sx+cx, v.co.y*sy+cy, v.co.z*sz+cz))
    me = bpy.data.meshes.new("t"); t.to_mesh(me); t.free(); fbm.from_mesh(me); bpy.data.meshes.remove(me)
for cx, cy, _ in clusters:
    box(cx, cy, zmin+0.016, 0.165, 0.165, 0.032)                 # base plate
    box(cx, cy, zmin+0.095, foot_sz+0.05, foot_sz+0.05, 0.125)   # collar around the post
    for bx, by in ((0.058, 0.058), (-0.058, 0.058), (0.058, -0.058), (-0.058, -0.058)):
        box(cx+bx, cy+by, zmin+0.04, 0.022, 0.022, 0.02)         # bolt heads
fme = bpy.data.meshes.new("MetalFeet"); fbm.to_mesh(fme); fbm.free()
feet = bpy.data.objects.new("MetalFeet", fme); bpy.context.collection.objects.link(feet)
mm = bpy.data.materials.new("feet_metal"); mm.use_nodes = True
b = mm.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.045, 0.045, 0.05, 1)
b.inputs["Metallic"].default_value = 1.0; b.inputs["Roughness"].default_value = 0.44
feet.data.materials.append(mm)
feet.select_set(True); bpy.context.view_layer.objects.active = feet
bpy.ops.object.shade_flat()
feet.modifiers.new("bev", 'BEVEL').width = 0.004; bpy.ops.object.modifier_apply(modifier="bev")
# cube-project UVs so the metal roughness/normal has coords if ever swapped
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.cube_project(cube_size=0.2); bpy.ops.object.mode_set(mode='OBJECT'); feet.select_set(False)
print("[addons] metal feet added")

# ---- ground displacement: bake real relief into the dense flat Ground grid ----
g = bpy.data.objects.get("Ground")
src = bpy.data.images.get("ground_col")           # its own grass colour -> height (aligned to the tufts)
# centre the displacement on the image's MEAN luminance so the ground undulates AROUND the
# post plane (z=0) instead of sinking below it; then push strength up for visible relief.
import numpy as np
w_, h_ = src.size; a = np.empty(w_*h_*4, dtype=np.float32); src.pixels.foreach_get(a); a = a.reshape(-1, 4)
lum = 0.2126*a[:,0] + 0.7152*a[:,1] + 0.0722*a[:,2]; mid = float(lum.mean())
# denser grid first so the taller displacement resolves as grassy relief, not coarse facets
g.select_set(True); bpy.context.view_layer.objects.active = g
sub = g.modifiers.new("sub", 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 1
bpy.ops.object.modifier_apply(modifier="sub")
disp_tex = bpy.data.textures.new("ground_disp", 'IMAGE'); disp_tex.image = src
d = g.modifiers.new("disp", 'DISPLACE')
d.texture = disp_tex; d.texture_coords = 'UV'
d.strength = 0.24                                 # was ~flat; grassy undulation (dialled back a notch)
d.mid_level = mid                                 # centred on mean -> balanced up/down around z=0
bpy.ops.object.shade_smooth()
bpy.ops.object.modifier_apply(modifier="disp"); g.select_set(False)
print(f"[addons] ground mid_level={mid:.3f}")

# ---- contact-shadow AO baked into the ground as vertex colour (feet ground into it) ----
feet_xy = [(c[0], c[1]) for c in clusters]
me = g.data
ca = me.color_attributes.new(name="AO", domain='POINT', type='BYTE_COLOR')
for i, v in enumerate(me.vertices):
    wx, wy = v.co.x, v.co.y                        # grid built at origin -> local == world XY
    dmin = min(math.hypot(wx-fx, wy-fy) for fx, fy in feet_xy)
    ao = 1.0
    if dmin < 0.40:                                # tight dark halo right under each foot plate
        t = dmin / 0.40; ao *= 0.28 + 0.72 * t * t
    rr = math.hypot(wx, wy)
    if rr < 2.55:                                  # broad soft occlusion under the whole booth
        ao *= 0.82 + 0.18 * min(1.0, rr / 2.55)
    ca.data[i].color = (ao, ao, ao, 1.0)
# multiply the vertex AO into the ground's base colour
gmat = g.data.materials[0]; gt = gmat.node_tree
bsdf = next(n for n in gt.nodes if n.type == 'BSDF_PRINCIPLED')
colnode = next(n for n in gt.nodes if n.type == 'TEX_IMAGE' and n.image and n.image.name.startswith("ground_col"))
vc = gt.nodes.new('ShaderNodeVertexColor'); vc.layer_name = "AO"
mix = gt.nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 1.0
gt.links.new(colnode.outputs['Color'], mix.inputs[1])
gt.links.new(vc.outputs['Color'], mix.inputs[2])
gt.links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])
print("[addons] contact-shadow vertex AO baked into ground")
zr = [ (g.matrix_world @ v.co).z for v in g.data.vertices ]
print(f"[addons] ground displaced: Z range now [{min(zr):.3f},{max(zr):.3f}]")

bpy.ops.export_scene.gltf(filepath=GLB, export_format='GLB', export_yup=True, use_selection=False,
                          export_vertex_color='ACTIVE')
print(f"[addons] exported {GLB}")
