"""render.py - mesh every shape in shapes.CATALOG, light it, render, and save a .blend.

    blender -b --python render.py -- [--res 200] [--samples 128] [--size 1400] [--only Pod ...]
                                     [--quick] [--no-render] [--out renders] [--blend sdf_shapes.blend]
"""
import argparse
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sdf  # noqa: E402
import shapes  # noqa: E402


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=200)
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--size", type=int, default=1400)
    ap.add_argument("--out", default=os.path.join(HERE, "renders"))
    ap.add_argument("--blend", default=os.path.join(HERE, "sdf_shapes.blend"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-nodes", action="store_true", help="skip the geometry-nodes object")
    ap.add_argument("--no-individual", action="store_true", help="cats: skip per-character renders")
    ap.add_argument("--no-scene", action="store_true", help="cats: skip the group scene render")
    ap.add_argument("--frames", type=int, default=96, help="rig: animation length")
    ap.add_argument("--preview", action="store_true", help="rig: render an EEVEE preview animation")
    ap.add_argument("--no-video", action="store_true", help="rig: with --preview, render the stills but not the video")
    a = ap.parse_args(argv)
    if a.quick:
        a.res, a.samples, a.size = 64, 16, 480
    return a


def setup_render(scene, samples, size):
    scene.render.engine = "CYCLES"
    cyc = scene.cycles
    cyc.samples = samples
    cyc.use_denoising = True
    try:
        cyc.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        cyc.device = "GPU"
    except Exception as e:
        print("GPU setup failed, using CPU:", e)
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass


WORLD_COLOR = (0.78, 0.81, 0.86)


def make_world():
    w = bpy.data.worlds.new("Studio")
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value = (*WORLD_COLOR, 1)
    bg.inputs["Strength"].default_value = 0.42
    if not bg.outputs[0].links:
        nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return w


def principled(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    if b is None:
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = nt.nodes.get("Material Output") or nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(b.outputs[0], out.inputs["Surface"])
    return m, b


def clay_material(name, color):
    m, b = principled(name)
    for k, v in {"Base Color": (*color, 1), "Roughness": 0.38, "Subsurface Weight": 0.18,
                 "Subsurface Radius": (0.12, 0.06, 0.035), "Subsurface Scale": 0.2,
                 "Coat Weight": 0.15, "Coat Roughness": 0.25}.items():
        if k in b.inputs:
            b.inputs[k].default_value = v
    return m


def floor_material():
    m, b = principled("Floor")
    b.inputs["Base Color"].default_value = (*WORLD_COLOR, 1)
    b.inputs["Roughness"].default_value = 1.0
    return m


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def aim(ob, target):
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()


def add_light(name, loc, energy, size, color=(1, 1, 1)):
    L = bpy.data.lights.new(name, "AREA")
    L.energy, L.size, L.color = energy, size, color
    ob = link(bpy.data.objects.new(name, L))
    ob.location = loc
    return ob


def place_lights(lights, center, scale):
    for ob, base in lights:
        ob.location = Vector(center) + Vector(base) * scale
        ob.data.energy = ob["base_energy"] * scale * scale
        ob.data.size = ob["base_size"] * scale
        aim(ob, center)


def add_camera(lens=50):
    cam = bpy.data.cameras.new("Camera")
    cam.lens, cam.sensor_width = lens, 36
    ob = link(bpy.data.objects.new("Camera", cam))
    bpy.context.scene.camera = ob
    return ob


def frame(cam, center, radius, direction=(1, -1.25, 0.72), pad=0.85):
    fov = 2 * math.atan(18 / cam.data.lens)
    dvec = Vector(direction).normalized()
    cam.location = Vector(center) + dvec * (radius / math.sin(fov / 2) * pad)
    aim(cam, center)


def bounds(objs):
    bpy.context.view_layer.update()  # refresh matrix_world after moving objects
    dg = bpy.context.evaluated_depsgraph_get()
    pts = np.array([[*(o.matrix_world @ Vector(c))] for o in objs for c in o.evaluated_get(dg).bound_box])
    lo, hi = pts.min(0), pts.max(0)
    return (lo + hi) / 2, float(np.linalg.norm(hi - lo) / 2), lo, hi


def build(name, fn, color, res):
    t = time.time()
    ob = sdf.add_object(name, fn, bounds=shapes.BOUNDS, res=res)
    ob.data.materials.append(clay_material(name, color))
    print(f"[{name}] {len(ob.data.vertices)} verts, {len(ob.data.polygons)} faces, {time.time() - t:.1f}s")
    return ob


def render_to(scene, path):
    scene.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[render] {os.path.basename(path)} {time.time() - t:.1f}s")


def main():
    a = parse()
    if a.quick:  # never clobber the full-quality outputs with a preview
        a.out, a.blend = os.path.join(a.out, "quick"), a.blend.replace(".blend", "_quick.blend")
    os.makedirs(a.out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    setup_render(scene, a.samples, a.size)
    scene.world = make_world()

    objs = [build(n, fn, c, a.res) for n, fn, c in shapes.CATALOG if not a.only or n in a.only]
    if not a.no_nodes and (not a.only or "NodeSDF" in a.only):
        import nodes_sdf
        ob = nodes_sdf.add_object("NodeSDF", clay_material("NodeSDF", (0.50, 0.32, 0.66)))
        print(f"[NodeSDF] {nodes_sdf.evaluated_vertex_count(ob)} verts (pure geometry nodes)")
        objs.append(ob)

    floor = link(bpy.data.objects.new("Floor", bpy.data.meshes.new("Floor")))
    floor.data.from_pydata([(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)], [], [(0, 1, 2, 3)])
    floor.data.materials.append(floor_material())

    lights = [(add_light("Key", (0, 0, 0), 0, 0, (1, 0.93, 0.85)), (2.6, -3.2, 3.6)),
              (add_light("Rim", (0, 0, 0), 0, 0, (0.78, 0.88, 1)), (-3.2, 2.8, 2.6)),
              (add_light("Fill", (0, 0, 0), 0, 0, (1, 1, 1)), (-3.0, -2.4, 0.6))]
    for (ob, _), (e, s) in zip(lights, [(520, 2.6), (320, 1.8), (110, 3.5)]):
        ob["base_energy"], ob["base_size"] = e, s
    cam = add_camera(50)

    if not a.no_render:
        for ob in objs:
            for o in objs:
                o.hide_render = o is not ob
            c, r, lo, hi = bounds([ob])
            floor.location.z = lo[2] - 0.01
            place_lights(lights, c, 1.0)
            frame(cam, c, r)
            render_to(scene, os.path.join(a.out, f"{ob.name}.png"))

    # gallery layout: a row, shared floor, saved into the .blend
    for i, ob in enumerate(objs):
        ob.hide_render = False
        ob.location.x = (i - (len(objs) - 1) / 2) * 3.0
    c, r, lo, hi = bounds(objs)
    floor.location.z = lo[2] - 0.01
    place_lights(lights, c, 2.2)
    cam.data.lens = 35
    frame(cam, c, r, direction=(0.08, -1.0, 0.42), pad=1.0)
    if not a.no_render and len(objs) > 1:
        scene.render.resolution_x = int(a.size * 2.0)
        render_to(scene, os.path.join(a.out, "gallery.png"))
    bpy.ops.wm.save_as_mainfile(filepath=a.blend)
    print("[saved]", a.blend)


if __name__ == "__main__":
    main()
