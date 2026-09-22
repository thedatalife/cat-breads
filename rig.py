"""rig.py - armatures for the SDF cats, with skin weights derived from the SDF parts, plus an idle animation.

    blender -b --python rig.py -- [--only ...] [--quick] [--frames 96] [--preview] [--size 640]

Bones come from each character's recorded anatomy (body, head, ears, tail). Skin weights are a
softmin over the distances to the tagged SDF parts, so the blend between head and body follows the
same smooth union that shaped the mesh; the tail's weight is split along its arc length into three
chained bones. Every bone gets F-curve noise so the group idles on its own: breathing, head turns,
ear twitches and tail sways with independent phases. Output: cat_breads_rigged.blend, and with
--preview an EEVEE animation in renders/anim/.
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
import render_cats  # noqa: E402

TAU = 0.05  # softmin temperature for skin weights, in model units
TAIL_BONES = 3


def action_fcurves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                out.extend(cb.fcurves)
    return out


def arc_samples(points, n):
    """n+1 points evenly spaced by arc length along a polyline."""
    pts = np.asarray(points, np.float32)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    out = []
    for i in range(n + 1):
        s = cum[-1] * i / n
        k = min(int(np.searchsorted(cum, s, side="right")) - 1, len(seg) - 1)
        h = 0.0 if seg[k] == 0 else (s - cum[k]) / seg[k]
        out.append(pts[k] + (pts[k + 1] - pts[k]) * h)
    return out


def build_armature(name, model, scale, offset, root):
    """Bones in the character's frame: body from floor to body centre, head from the neck, ears, tail chain."""
    A = model.anatomy
    off = np.asarray(offset, np.float32)

    def P(v):
        return Vector(tuple(np.asarray(v, np.float32) * scale + off))

    arm = bpy.data.armatures.new(f"{name}.rig")
    ob = render.link(bpy.data.objects.new(f"{name}.rig", arm))
    ob.parent = root
    ob.show_in_front = True
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    bc, br = A["body"]
    hc, hr = A["head"]
    body = eb.new("body")
    body.head, body.tail = P((bc[0], bc[1], 0.0)), P(bc)
    head = eb.new("head")
    head.head, head.tail = P((bc + hc) / 2), P(hc + [0, 0, hr[2]])
    head.parent = body
    for side in ("L", "R"):
        if f"ear.{side}" in A:
            base, tip = A[f"ear.{side}"]
            e = eb.new(f"ear.{side}")
            e.head, e.tail = P(base), P(tip)
            e.parent = head
    for side in ("L", "R"):  # vertical eye bones: scaling along the bone squashes the eye into a blink
        if f"eye.{side}" in A:
            c, r = A[f"eye.{side}"]
            e = eb.new(f"eye.{side}")
            e.head, e.tail = P(c), P(c + [0, 0, r])
            e.parent = head
    if "tail" in A:
        samples = arc_samples(A["tail"], TAIL_BONES)
        prev = body
        for i in range(TAIL_BONES):
            t = eb.new(f"tail.{i + 1:03d}")
            t.head, t.tail = P(samples[i]), P(samples[i + 1])
            t.parent = prev
            t.use_connect = i > 0
            prev = t
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def skin(ob, model, scale, offset, arm_ob, tau=TAU):
    """Vertex groups from softmin over the tagged part distances; the tail split by arc length."""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    p = (co.reshape(-1, 3) - np.asarray(offset, np.float32)) / np.float32(scale)
    tags = [t for t in ("body", "head", "ear.L", "ear.R", "tail") if t in model.anatomy]
    D = np.stack([model.tag_distance(p, t) for t in tags], -1)
    w = np.exp(-(D - D.min(-1, keepdims=True)) / np.float32(tau))
    w /= w.sum(-1, keepdims=True)
    groups = {}
    for side in ("L", "R"):  # eyes bind sharply (a 1 cm falloff), and take their share from the other bones
        if f"eye.{side}" in model.anatomy:
            we = np.clip(1 - model.tag_distance(p, f"eye.{side}") / np.float32(0.010), 0, 1)
            groups[f"eye.{side}"] = we
            w *= (1 - we)[:, None]
    for j, t in enumerate(tags):
        if t == "tail":
            _, tt = cats.polyline_param(p, model.anatomy["tail"])
            centers = (np.arange(TAIL_BONES) + 0.5) / TAIL_BONES
            for i in range(TAIL_BONES):
                hat = np.interp(tt, centers, np.eye(TAIL_BONES)[i])
                groups[f"tail.{i + 1:03d}"] = w[:, j] * hat
        else:
            groups[t] = w[:, j]
    for bone, weights in groups.items():
        vg = ob.vertex_groups.new(name=bone)
        idx = np.nonzero(weights > 1e-3)[0]
        for i in idx:  # one call per vertex; fine at this size
            vg.add([int(i)], float(weights[i]), "REPLACE")
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_ob
    ob.modifiers.move(len(ob.modifiers) - 1, 0)  # deform before the smoothing modifier


def attach_all(ob, arm_ob, bone="body"):
    """Rigid parts that ride along (wings): everything on one bone."""
    vg = ob.vertex_groups.new(name=bone)
    vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_ob
    ob.modifiers.move(len(ob.modifiers) - 1, 0)


def idle(arm_ob, rng, frames):
    """F-curve noise on every bone: the cat breathes, looks around, twitches and sways on its own."""
    for pb in arm_ob.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.keyframe_insert(data_path="rotation_euler", frame=1)
        pb.keyframe_insert(data_path="scale", frame=1)
    fcs = {}
    for fc in action_fcurves(arm_ob.animation_data.action):
        bone = fc.data_path.split('"')[1]
        fcs[(bone, fc.data_path.rsplit(".", 1)[1], fc.array_index)] = fc

    def noise(bone, path, idx, strength, scale, phase=None, offset=None):
        fc = fcs.get((bone, path, idx))
        if fc is None:
            return
        m = fc.modifiers.new("NOISE")
        m.strength, m.scale = strength, scale
        m.phase = rng.uniform(0, 100) if phase is None else phase
        m.offset = rng.uniform(0, 1000) if offset is None else offset

    deg = math.radians
    breath = rng.uniform(0, 100)
    noise("body", "scale", 2, 0.05, 40, phase=breath, offset=0)      # breathing along the bone axis ...
    noise("body", "scale", 0, -0.025, 40, phase=breath, offset=0)    # ... with a little squash sideways
    noise("body", "scale", 1, -0.025, 40, phase=breath, offset=0)
    noise("body", "rotation_euler", 2, deg(6), 70)                    # slow sway
    noise("body", "rotation_euler", 1, deg(4), 55)
    noise("head", "rotation_euler", 0, deg(10), 45)                   # nod
    noise("head", "rotation_euler", 2, deg(18), 75)                   # look around
    noise("head", "rotation_euler", 1, deg(7), 60)                    # tilt
    for side in ("L", "R"):
        noise(f"ear.{side}", "rotation_euler", 0, deg(16), 14)        # quick twitches
        noise(f"ear.{side}", "rotation_euler", 1, deg(8), 20)
    base = rng.uniform(0, 1000)
    for i in range(TAIL_BONES):
        noise(f"tail.{i + 1:03d}", "rotation_euler", 0, deg(16), 38, offset=base + i * 9)  # a wave travels up the tail
        noise(f"tail.{i + 1:03d}", "rotation_euler", 1, deg(12), 46, offset=base + 500 + i * 9)


def eevee_glass(scene):
    """EEVEE previews: with the world nearly off, refraction has nothing to show, so glass becomes a tinted
    translucent surface instead. Only applied at preview time; the saved .blend keeps the Cycles glass."""
    for m in bpy.data.materials:
        b = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
        if b is not None and "Transmission Weight" in b.inputs and b.inputs["Transmission Weight"].default_value > 0.5:
            b.inputs["Transmission Weight"].default_value = 0.0
            b.inputs["Alpha"].default_value = 0.22
            b.inputs["Roughness"].default_value = 0.05
            b.inputs["Coat Weight"].default_value = 0.6
            for attr, val in (("surface_render_method", "BLENDED"), ("use_transparency_overlap", True)):
                try:
                    setattr(m, attr, val)
                except Exception:
                    pass


def rig_character(name, root, obs, parts, rng, frames):
    by_name = {p["name"]: p for p in parts}
    skinned = [p for p in parts if p["model"].anatomy]
    if not skinned:
        return None
    main = skinned[0]
    arm_ob = build_armature(name, main["model"], main["scale"], main["offset"], root)
    for ob in obs:
        pname = ob.name.split(".", 1)[1]
        p = by_name[pname]
        if p["model"].anatomy:
            skin(ob, p["model"], p["scale"], p["offset"], arm_ob)
        elif pname in ("wings", "coin"):  # carried along with the body
            attach_all(ob, arm_ob)
    idle(arm_ob, rng, frames)
    return arm_ob


def main():
    a = render.parse()
    frames, preview = a.frames, a.preview
    size = a.size if "--size" in sys.argv else 640
    if "--res" not in sys.argv:
        a.res = 224
    if a.quick:
        a.res = 96
    out = os.path.join(HERE, "renders", "anim")
    blend = os.path.join(HERE, "cat_breads_rigged.blend")
    if a.quick:
        out, blend = os.path.join(out, "quick"), blend.replace(".blend", "_quick.blend")
    os.makedirs(out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    render.setup_render(scene, a.samples, size)
    render_cats.warm_world(scene)
    scene.frame_start, scene.frame_end = 1, frames
    scene.render.fps = 24

    chars = [render_cats.build_character(n, fn, a.res) for n, fn in cats.CHARACTERS if not a.only or n in a.only]
    rng = np.random.default_rng(11)
    t = time.time()
    for root, obs in chars:
        rig_character(root.name, root, obs, render_cats.LAST_PARTS[root.name], rng, frames)
    print(f"[rig] {len(chars)} characters rigged in {time.time() - t:.1f}s")

    backdrop = render_cats.cyclorama()
    lights = render_cats.rig()
    cam = render.add_camera(45)
    layout = cats.hangout_layout()
    for i, (root, obs) in enumerate(chars):
        x, y, yaw = layout.get(root.name, ((i - (len(chars) - 1) / 2) * 2.4, 0.0, 0.0))
        root.location = (x, y, 0)
        root.rotation_euler.z = math.radians(root["yaw"] + yaw)
    all_obs = [o for _, obs in chars for o in obs]
    c, r, lo, hi = render.bounds(all_obs)
    scale = 3.0 if len(chars) > 6 else 1.0 + 0.35 * (len(chars) - 1)
    render_cats.place_rig(lights, backdrop, c, lo, hi, scale)
    scene.render.resolution_x = int(size * 2.2)
    render.frame(cam, (c[0], c[1], c[2] * 0.6), r, direction=(0.05, -1.0, 0.30), pad=0.78)
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("[saved]", blend)

    if preview:
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = 48
        eevee_glass(scene)
        scene.render.image_settings.file_format = "PNG"
        for f in (1, frames // 2, frames):  # stills to look at
            scene.frame_set(f)
            render.render_to(scene, os.path.join(out, f"frame_{f:04d}.png"))
        if a.no_video:
            return
        try:
            scene.render.image_settings.media_type = "VIDEO"  # Blender 4.5+: video is a media type, then a format
        except Exception:
            pass
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "HIGH"
        scene.render.filepath = os.path.join(out, "idle_")
        t = time.time()
        bpy.ops.render.render(animation=True)
        print(f"[anim] {frames} frames in {time.time() - t:.1f}s ->", out)


if __name__ == "__main__":
    main()
