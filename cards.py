"""cards.py - turn each cat into an index card (render + handwritten label) and lay them out like the photo.

    blender -b --python cards.py -- --stage cats     [--only ...] [--quick]   # transparent renders with a contact shadow
    blender -b --python cards.py -- --stage labels   [--only ...]             # marker-font titles on transparent PNGs
    blender -b --python cards.py -- --stage compose                           # renders/cards/NN_Name.jpg + cat_breads_cards.jpg
    blender -b --python cards.py -- --stage all
"""
import argparse
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cats  # noqa: E402
import render  # noqa: E402
import render_cats  # noqa: E402
import sdf  # noqa: E402

OUT = os.path.join(HERE, "renders", "cards")
CAT_PX, CARD_W, CARD_H, LABEL_H = 1000, 1000, 1560, 420
PAPER = (0.985, 0.975, 0.955)
CARD_BG = {"Mascot": (0.36, 0.76, 0.88)}  # the cover card is painted blue
FONTS = ["/System/Library/Fonts/Supplemental/Chalkboard.ttc", "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
         "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"]

# Titles as written on the cards, spelling included. Second item is a footnote written lower on the card.
LABELS = {
    "Mascot": ("cat breads", None), "Siamese": ("The SIAMESE", None), "Sphynx": ("The SPHYNX", None),
    "NorwegianForest": ("the NORWEGIN FOREST", None), "Catuccino": ("Catuccino", None), "Wanderer": ("The wanderer", None),
    "DayCat": ("the Day cat", None), "InvestigatorOne": ("the invetigator one", None), "LuckyCat": ("The Lucky cat", None),
    "Explorer": ("the EXPLORER", None), "Dozer": ("The DOZER", None), "Stretcher": ("The investogater allso the stretcher", None),
    "ShowOff": ("the show of!", "AND NO FARTING"), "BoxTester": ("the Box tester", None), "NatureLover": ("The Nature Lover", None),
    "LargeHearted": ("the Large HEARTED", None), "KittyRoll": ("kitty ROLL", None), "AngelCat": ("The ANGEL CAT", None),
    "DevilCat": ("The DEVIL cat", None), "Unimeow": ("The UNIMEOW", None), "BumbleCat": ("The BUMBLE cat", None),
    "HolidayKitty": ("The Holiday Kitty", None), "Accountcat": ("The Accountcat", None),
}
ORDER = [n for n, _ in cats.CHARACTERS]  # already the photo's order, row by row


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["cats", "labels", "compose", "all"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--res", type=int, default=224)
    ap.add_argument("--font", type=int, default=1, help="index into FONTS (1 = Comic Sans MS Bold, closest to marker)")
    a = ap.parse_args(argv)
    if a.quick:
        a.res, a.samples = 96, 16
    return a


def names_for(a):
    return [n for n in ORDER if not a.only or n in a.only]


# ---------------------------------------------------------------- stage: cats
def stage_cats(a):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    render.setup_render(scene, a.samples, CAT_PX)
    render_cats.warm_world(scene)
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0  # a dome light would haze the catcher
    chars = [render_cats.build_character(n, fn, a.res) for n, fn in cats.CHARACTERS if n in names_for(a)]
    backdrop = render_cats.cyclorama()
    backdrop.is_shadow_catcher = True  # only the contact shadow survives onto the card
    lights = render_cats.rig()
    for ob in lights:
        if ob.name == "Fill":
            ob["base_energy"] = ob["base_energy"] * 1.6  # make up for the missing dome light
    cam = render.add_camera(55)
    os.makedirs(os.path.join(OUT, "cats"), exist_ok=True)
    for root, obs in chars:
        for r2, obs2 in chars:
            for o in obs2:
                o.hide_render = r2 is not root
        c, r, lo, hi = render.bounds(obs)
        render_cats.place_rig(lights, backdrop, c, lo, hi, 1.0)
        render.frame(cam, c, r, direction=(0.7, -1.0, 0.45), pad=0.9)
        render.render_to(scene, os.path.join(OUT, "cats", f"{root.name}.png"))


# ---------------------------------------------------------------- stage: labels
def load_font(index):
    for p in FONTS[index:] + FONTS[:index]:
        if os.path.exists(p):
            try:
                return bpy.data.fonts.load(p)
            except Exception:
                continue
    return None


def text_object(body, font, size, width, mat, name="T"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    if font is not None:
        cu.font = font
    cu.size = size
    cu.align_x = "LEFT"
    cu.text_boxes[0].width = width
    cu.materials.append(mat)
    ob = render.link(bpy.data.objects.new(name, cu))
    return ob


def stage_labels(a):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    render.setup_render(scene, 48, CARD_W)
    scene.cycles.use_denoising = False
    scene.render.resolution_y = LABEL_H
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    font = load_font(a.font)
    print("[font]", font.name if font else "Blender default")
    cam = bpy.data.cameras.new("Cam")
    cam.type = "ORTHO"
    cam.ortho_scale = 10.0  # 10 units across CARD_W pixels
    camob = render.link(bpy.data.objects.new("Cam", cam))
    camob.location = (0, 0, 10)
    scene.camera = camob
    ink = {}
    for nm, col in (("ink", (0.04, 0.04, 0.05)), ("pencil", (0.42, 0.40, 0.38))):
        m = bpy.data.materials.new(nm)
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            if n.bl_idname != "ShaderNodeOutputMaterial":
                nt.nodes.remove(n)
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*col, 1)
        nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
        ink[nm] = m
    os.makedirs(os.path.join(OUT, "labels"), exist_ok=True)
    top, height_limit = 2.0, 3.9
    for name in names_for(a):
        title, footer = LABELS[name]
        for text, tag, mat, size in ((title, "title", ink["ink"], 1.32), (footer, "footer", ink["pencil"], 0.66)):
            if not text:
                continue
            ob = text_object(text, font, size, 9.0, mat)
            while True:  # shrink until the wrapped block fits the label region
                ob.location = (-4.5, top - size * 0.85, 0)
                bpy.context.view_layer.update()
                if ob.dimensions.y <= height_limit or size <= 0.5:
                    break
                size -= 0.05
                ob.data.size = size
            render.render_to(scene, os.path.join(OUT, "labels", f"{name}_{tag}.png"))
            bpy.data.objects.remove(ob)


# ---------------------------------------------------------------- stage: compose
def load_rgba(path, clean_alpha=False):
    """Top-down float array (H, W, 4). clean_alpha removes the faint uniform alpha a shadow catcher leaves."""
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[::-1].copy()
    bpy.data.images.remove(img)
    if clean_alpha:
        knee = max(float(np.median(px[:30, :30, 3])), 0.015)
        px[..., 3] = np.clip((px[..., 3] - knee) / (1 - knee), 0, 1)
    return px


def over(dst, src, x, y):
    """Alpha-composite src onto dst with its top-left corner at (x, y); anything off-canvas is cropped."""
    H, W = dst.shape[:2]
    h, w = src.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    a = s[..., 3:4]
    region = dst[y0:y1, x0:x1]
    region[:] = s[..., :3] * a + region * (1 - a)


def to_image(arr, name):
    H, W = arr.shape[:2]
    img = bpy.data.images.new(name, W, H, alpha=False)
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = np.clip(arr[::-1], 0, 1)
    img.pixels = rgba.ravel()
    return img


def save_jpg(img, path, quality=92):
    img.file_format = "JPEG"
    img.filepath_raw = path
    img.save(quality=quality)


def image_array(img):
    w, h = img.size
    return np.array(img.pixels[:], np.float32).reshape(h, w, 4)[::-1, :, :3].copy()


def box_blur(mask, r):
    pad = np.pad(mask, r, mode="edge")
    c = np.cumsum(np.cumsum(pad, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    H, W = mask.shape
    k = 2 * r + 1
    out = c[k:k + H, k:k + W] - c[:H, k:k + W] - c[k:k + H, :W] + c[:H, :W]
    return out / (k * k)


def wood(H, W, seed=2):
    """Warm boards with a soft grain, like the table in the photo."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    p = np.stack([xs / 260, ys / 26, np.zeros_like(xs)], -1).reshape(-1, 3)
    grain = sdf.fbm3(p, octaves=3, seed=seed).reshape(H, W)
    boards = 0.5 + 0.5 * np.sin(ys / 190 + 0.35 * grain)
    base = np.array([0.56, 0.34, 0.17], np.float32)
    tone = 0.86 + 0.16 * grain + 0.06 * boards
    return base[None, None, :] * tone[..., None]


def stage_compose(a):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    os.makedirs(OUT, exist_ok=True)
    cards = []
    for i, name in enumerate(ORDER):
        card = np.empty((CARD_H, CARD_W, 3), np.float32)
        card[:] = CARD_BG.get(name, PAPER)
        over(card, load_rgba(os.path.join(OUT, "labels", f"{name}_title.png")), 0, 70)
        over(card, load_rgba(os.path.join(OUT, "cats", f"{name}.png"), clean_alpha=True), 0, CARD_H - CAT_PX - 60)
        footer = os.path.join(OUT, "labels", f"{name}_footer.png")
        if os.path.exists(footer):
            over(card, load_rgba(footer), 40, CARD_H - 250)
        img = to_image(card, f"card_{name}")
        save_jpg(img, os.path.join(OUT, f"{i + 1:02d}_{name}.jpg"))
        cards.append(img)
        print(f"[card] {i + 1:02d}_{name}.jpg")

    # the photo layout: five columns, cards in reading order, on a wooden table
    cols, gap, cw = 5, 46, 430
    ch = int(round(cw * CARD_H / CARD_W))
    rows = (len(cards) + cols - 1) // cols
    W, H = cols * cw + (cols + 1) * gap, rows * ch + (rows + 1) * gap
    canvas = wood(H, W)
    shadow = np.zeros((H, W), np.float32)
    for i in range(len(cards)):
        r, c = divmod(i, cols)
        x, y = gap + c * (cw + gap), gap + r * (ch + gap)
        shadow[y + 14:y + ch + 14, x + 10:x + cw + 10] = 1
    canvas *= (1 - 0.45 * box_blur(shadow, 12))[..., None]
    for i, img in enumerate(cards):
        r, c = divmod(i, cols)
        x, y = gap + c * (cw + gap), gap + r * (ch + gap)
        img.scale(cw, ch)
        canvas[y:y + ch, x:x + cw] = image_array(img)
    save_jpg(to_image(canvas, "layout"), os.path.join(OUT, "cat_breads_cards.jpg"), quality=90)
    print("[layout]", os.path.join(OUT, "cat_breads_cards.jpg"), f"{W}x{H}")


def main():
    a = parse()
    if a.stage in ("cats", "all"):
        stage_cats(a)
    if a.stage in ("labels", "all"):
        stage_labels(a)
    if a.stage in ("compose", "all"):
        stage_compose(a)


if __name__ == "__main__":
    main()
