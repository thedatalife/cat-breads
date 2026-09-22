"""export_web.py - export each rigged character as a Draco-compressed GLB for the Three.js lounge.

    blender -b cat_breads_rigged.blend --python export_web.py -- [--target 24000] [--only Name ...]

Each character is exported at the origin, upright, as its own file (root empty, decimated skinned
meshes, armature). The lounge layout (position + yaw per character) goes to web/layout.json.
"""
import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cats  # noqa: E402

OUT = os.path.join(HERE, "web", "models")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
target = int(argv[argv.index("--target") + 1]) if "--target" in argv else 24000
only = argv[argv.index("--only") + 1:] if "--only" in argv else None
os.makedirs(OUT, exist_ok=True)

names = [n for n, _ in cats.CHARACTERS if not only or n in only]
layout = {}
for name in names:
    root = bpy.data.objects[name]
    children = [o for o in bpy.data.objects if o.parent == root]
    layout[name] = {"x": round(root.location.x, 3), "y": round(root.location.y, 3), "yaw": round(math.degrees(root.rotation_euler.z), 2)}
    root.location = (0, 0, 0)
    root.rotation_euler = (0, 0, 0)
    for c in children:
        if c.type == "MESH" and len(c.data.vertices) > target:
            d = c.modifiers.new("Decimate", "DECIMATE")
            d.ratio = target / len(c.data.vertices)
            d.use_collapse_triangulate = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in [root] + children:
        o.select_set(True)
    bpy.context.view_layer.objects.active = root
    path = os.path.join(OUT, f"{name}.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_animations=False,
                              export_skins=True, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
                              export_vertex_color="MATERIAL", export_yup=True, export_texcoords=False, export_normals=True,
                              export_lights=False, export_cameras=False, export_rest_position_armature=True)
    print(f"[glb] {name}: {os.path.getsize(path) / 1e6:.2f} MB")
with open(os.path.join(HERE, "web", "layout.json"), "w") as f:
    json.dump(layout, f, indent=1)
print("[layout]", len(layout), "characters")
