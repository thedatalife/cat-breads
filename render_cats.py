"""render_cats.py - build the SDF cat characters, render each one and the group scene, save cat_breads.blend.

    blender -b --python render_cats.py -- [--res 224] [--samples 128] [--size 1400] [--only LuckyCat ...]
                                          [--quick] [--no-individual] [--no-scene]
"""
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cats  # noqa: E402
import render  # noqa: E402
import sdf  # noqa: E402

PRESETS = {
    "clay": {"Roughness": 0.50, "Subsurface Weight": 0.06, "Subsurface Radius": (0.1, 0.05, 0.03), "Subsurface Scale": 0.15,
             "Coat Weight": 0.05, "Coat Roughness": 0.35},
    "backdrop": {"Roughness": 0.92, "Specular IOR Level": 0.2},
    "ceramic": {"Roughness": 0.12, "Coat Weight": 0.9, "Coat Roughness": 0.05, "Subsurface Weight": 0.05},
    "gold": {"Metallic": 1.0, "Roughness": 0.25},
    "wing": {"Roughness": 0.08, "Alpha": 0.42, "Coat Weight": 0.5, "Coat Roughness": 0.05},
    "glass": {"Roughness": 0.03, "Transmission Weight": 1.0, "IOR": 1.45, "Coat Weight": 0.2},
}


def vcol_material(name, preset):
    m, b = render.principled(name)
    vc = m.node_tree.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    m.node_tree.links.new(vc.outputs["Color"], b.inputs["Base Color"])
    for k, v in PRESETS[preset].items():
        if k in b.inputs:
            b.inputs[k].default_value = v
    return m


BACK_BOTTOM = (0.90, 0.79, 0.65)  # warm cream floor
BACK_TOP = (0.58, 0.28, 0.21)     # deep terracotta wall
GRADIENT_HEIGHT = 1.1             # per unit of scene scale; repainted for every render


def cyclorama(width=140.0, front=-70.0, radius=4.5, height=18.0, segments=48):
    """A studio sweep: flat floor that curves up into a wall, with a warm vertex-colour gradient.

    Local origin sits at the start of the bend; move the object so the bend lands behind the subject.
    """
    prof = [(front, 0.0), (0.0, 0.0)]
    for i in range(1, segments + 1):
        a = (i / segments) * (math.pi / 2)
        prof.append((radius * math.sin(a), radius - radius * math.cos(a)))
    prof.append((radius, height))
    verts = [(x, y, z) for (y, z) in prof for x in (-width / 2, width / 2)]
    faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(prof) - 1)]
    me = bpy.data.meshes.new("Backdrop")
    me.from_pydata(verts, [], faces)
    me.update()
    me.shade_smooth()
    me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    ob = render.link(bpy.data.objects.new("Backdrop", me))
    ob.data.materials.append(vcol_material("Backdrop", "backdrop"))
    paint_backdrop(ob, GRADIENT_HEIGHT)
    return ob


def paint_backdrop(ob, gradient_height):
    """Cream on the floor rising to terracotta, completing `gradient_height` up the wall."""
    me = ob.data
    z = np.array([v.co.z for v in me.vertices], np.float32)
    tt = np.clip(z / gradient_height, 0, 1)
    tt = tt * tt * (3 - 2 * tt)
    rgba = np.ones((len(z), 4), np.float32)
    rgba[:, :3] = np.outer(1 - tt, BACK_BOTTOM) + np.outer(tt, BACK_TOP)
    me.color_attributes["Col"].data.foreach_set("color", rgba.ravel())


def warm_world(scene):
    scene.world = render.make_world()
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.95, 0.80, 0.66, 1)
    bg.inputs["Strength"].default_value = 0.08
    scene.view_settings.exposure = -0.45
    for look in ("AgX - Punchy", "AgX - High Contrast", "AgX - Medium High Contrast"):
        try:  # the enum is not introspectable in 5.2, but assignment works
            scene.view_settings.look = look
            break
        except Exception:
            continue


def rig():
    """Key, fill, rim and a backdrop glow. Positions/energies are relative; see place_rig()."""
    spec = [("Key", (1.0, 0.90, 0.78), (-5.0, -5.0, 7.0), 2400, 2.2, "subject"),
            ("Fill", (0.80, 0.88, 1.0), (5.5, -5.0, 2.5), 140, 6.0, "subject"),
            ("Rim", (1.0, 0.96, 0.90), (2.5, 6.5, 5.5), 700, 2.0, "subject"),
            ("Glow", (1.0, 0.85, 0.70), (0.0, -3.0, 9.0), 260, 5.0, "wall")]
    lights = []
    for name, color, pos, energy, size, target in spec:
        ob = render.add_light(name, (0, 0, 0), energy, size, color)
        ob["base_pos"], ob["base_energy"], ob["base_size"], ob["target"] = pos, energy, size, target
        lights.append(ob)
    return lights


def place_rig(lights, backdrop, center, lo, hi, scale):
    backdrop.location = (center[0], hi[1] + 0.7 * scale, lo[2] - 0.005)
    paint_backdrop(backdrop, GRADIENT_HEIGHT * scale)
    wall = (center[0], hi[1] + 0.7 * scale + 4.5, 2.2 * scale)
    for ob in lights:
        ob.location = Vector(center) + Vector(ob["base_pos"]) * scale
        ob.data.energy = ob["base_energy"] * scale * scale
        ob.data.size = ob["base_size"] * (math.sqrt(scale) if ob.name == "Key" else scale)  # key stays crisp
        render.aim(ob, wall if ob["target"] == "wall" else (center[0], center[1], center[2] * 0.7))


LAST_PARTS = {}  # character name -> the part specs it was built from (models, scale, offset), for rigging


def build_character(name, builder, res):
    t = time.time()
    spec = builder()
    parts, yaw = (spec["parts"], spec.get("yaw", 0.0)) if isinstance(spec, dict) else (spec, 0.0)
    LAST_PARTS[name] = parts
    root = render.link(bpy.data.objects.new(name, None))
    root.empty_display_size = 0.2
    root["yaw"] = yaw
    voxel = (cats.BOUNDS[1][0] - cats.BOUNDS[0][0]) / res
    obs = []
    for p in parts:
        lo, hi = (np.asarray(b, np.float32) for b in p["bounds"])
        r = tuple(max(8, int(round(s / voxel))) for s in (hi - lo))
        ob = sdf.add_object(f"{name}.{p['name']}", p["sdf"], bounds=(lo, hi), res=r, color_fn=p["color"])
        ob.data.materials.append(vcol_material(f"{name}.{p['name']}", p["material"]))
        ob.parent = root
        obs.append(ob)
    root.rotation_euler.z = math.radians(yaw)
    print(f"[{name}] {sum(len(o.data.vertices) for o in obs)} verts in {time.time() - t:.1f}s")
    return root, obs


def main():
    a = render.parse()
    if "--res" not in sys.argv:
        a.res = 224  # characters carry painted detail; a finer default grid than the abstract shapes
    if a.quick:
        a.res = 96
    out = os.path.join(HERE, "renders", "cats") if a.out == os.path.join(HERE, "renders") else a.out
    blend = os.path.join(HERE, "cat_breads.blend") if a.blend == os.path.join(HERE, "sdf_shapes.blend") else a.blend
    if a.quick:  # never clobber the full-quality outputs with a preview
        out, blend = os.path.join(out, "quick"), blend.replace(".blend", "_quick.blend")
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    render.setup_render(scene, a.samples, a.size)
    warm_world(scene)

    chars = [build_character(n, fn, a.res) for n, fn in cats.CHARACTERS if not a.only or n in a.only]

    backdrop = cyclorama()
    lights = rig()
    cam = render.add_camera(55)

    if not a.no_render and not a.no_individual:
        for root, obs in chars:
            for r2, obs2 in chars:
                for o in obs2:
                    o.hide_render = r2 is not root
            c, r, lo, hi = render.bounds(obs)
            place_rig(lights, backdrop, c, lo, hi, 1.0)
            render.frame(cam, c, r, direction=(0.85, -1.0, 0.5), pad=0.78)
            render.render_to(scene, os.path.join(out, f"{root.name}.png"))

    # group scene: everyone hanging out
    layout = cats.hangout_layout()
    for i, (root, obs) in enumerate(chars):
        for o in obs:
            o.hide_render = False
        x, y, yaw = layout.get(root.name, ((i - (len(chars) - 1) / 2) * 2.4, 0.0, 0.0))
        root.location = (x, y, 0)
        root.rotation_euler.z = math.radians(root["yaw"] + yaw)
    all_obs = [o for _, obs in chars for o in obs]
    c, r, lo, hi = render.bounds(all_obs)
    place_rig(lights, backdrop, c, lo, hi, 3.0)
    cam.data.lens = 45
    scene.render.resolution_x = int(a.size * 2.2)
    render.frame(cam, (c[0], c[1], c[2] * 0.6), r, direction=(0.05, -1.0, 0.30), pad=0.78)
    if not a.no_render and not a.no_scene and len(chars) > 1:
        render.render_to(scene, os.path.join(out, "hangout.png"))
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("[saved]", blend)


if __name__ == "__main__":
    main()
