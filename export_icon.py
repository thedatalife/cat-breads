"""Render the app icon: one SDF cat, face on, in the same warm studio as the cards.

    blender -b --python export_icon.py -- [--only Mascot] [--size 1024] [--samples 192] [--res 224]

Writes web/icons/icon-1024.png. `make_icons.sh` then derives the favicon, touch icon and manifest sizes.
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cats, render, render_cats  # noqa: E402


def main():
    a = render.parse()
    if "--size" not in sys.argv:
        a.size = 1024
    if "--samples" not in sys.argv:
        a.samples = 192
    if "--res" not in sys.argv:
        a.res = 224
    name = (a.only or ["Mascot"])[0]
    builder = dict(cats.CHARACTERS)[name]
    out = os.path.join(HERE, "web", "icons")
    os.makedirs(out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    render.setup_render(scene, a.samples, a.size)
    render_cats.warm_world(scene)
    root, obs = render_cats.build_character(name, builder, a.res)
    backdrop = render_cats.cyclorama()
    lights = render_cats.rig()
    cam = render.add_camera(70)  # a longer lens flatters the face

    c, r, lo, hi = render.bounds(obs)
    render_cats.place_rig(lights, backdrop, c, lo, hi, 1.0)
    h = hi[2] - lo[2]
    aim = (c[0], c[1], lo[2] + 0.52 * h)  # centre the square a little above the middle, on the face
    render.frame(cam, aim, r, direction=(0.10, -1.0, 0.34), pad=0.84)  # room for the rounded-corner and maskable crops
    render.render_to(scene, os.path.join(out, "icon-1024.png"))


if __name__ == "__main__":
    main()
