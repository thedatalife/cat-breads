"""export_sign.py - extrude and bevel a line of text in a system font and export it as web/models/sign.glb.

    blender -b --python export_sign.py -- "For Lane" "/System/Library/Fonts/Supplemental/SignPainter.ttc"
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
text = argv[0] if argv else "For Lane"
font_path = argv[1] if len(argv) > 1 else "/System/Library/Fonts/Supplemental/SignPainter.ttc"

bpy.ops.wm.read_factory_settings(use_empty=True)
cu = bpy.data.curves.new("Sign", "FONT")
cu.body = text
cu.font = bpy.data.fonts.load(font_path)
cu.size = 1.0
cu.align_x = "CENTER"
cu.align_y = "CENTER"
cu.extrude = 0.10          # half depth: the letters are 0.2 deep
cu.bevel_depth = 0.022     # rounded front and back edges
cu.bevel_resolution = 4
cu.resolution_u = 10
ob = bpy.data.objects.new("Sign", cu)
ob.rotation_euler = (1.5707963, 0, 0)  # stand the text up so it faces -Y in Blender, +Z in glTF (toward the camera)
bpy.context.scene.collection.objects.link(ob)
mat = bpy.data.materials.new("Sign")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.98, 0.93, 0.80, 1)
b.inputs["Roughness"].default_value = 0.25
b.inputs["Coat Weight"].default_value = 0.6
ob.data.materials.append(mat)
font_name = cu.font.name  # the curve is discarded by the conversion below
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
bpy.ops.object.convert(target="MESH")
bpy.ops.object.shade_smooth_by_angle(angle=0.6) if hasattr(bpy.ops.object, "shade_smooth_by_angle") else bpy.ops.object.shade_smooth()
dims = ob.dimensions
print(f"[sign] '{text}' in {font_name}: {len(ob.data.vertices)} verts, size {dims.x:.2f} x {dims.z:.2f} x {dims.y:.2f}")
out = os.path.join(HERE, "web", "models", "sign.glb")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True, export_animations=False,
                          export_draco_mesh_compression_enable=True, export_yup=True, export_texcoords=False, export_normals=True)
print("[glb]", out, f"{os.path.getsize(out) / 1e6:.2f} MB")
