"""contact_sheet.py - tile the per-character renders into one grid image (runs inside Blender).

    blender -b --python contact_sheet.py -- renders/cats/quick sheet.png 6 [tile_width]
"""
import glob
import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
folder, out, cols = argv[0], argv[1], int(argv[2]) if len(argv) > 2 else 6
tile = int(argv[3]) if len(argv) > 3 else None
files = sorted(f for f in glob.glob(os.path.join(folder, "*.png")) if os.path.basename(f) not in ("hangout.png", "lineup.png", "contact_sheet.png"))
imgs = [bpy.data.images.load(f) for f in files]
if tile:
    for img in imgs:
        img.scale(tile, int(round(img.size[1] * tile / img.size[0])))
w, h = imgs[0].size
rows = (len(imgs) + cols - 1) // cols
canvas = np.zeros((rows * h, cols * w, 4), np.float32)
canvas[..., 3] = 1
for i, img in enumerate(imgs):
    px = np.array(img.pixels[:], np.float32).reshape(img.size[1], img.size[0], 4)[:h, :w]
    r, c = divmod(i, cols)
    y0 = (rows - 1 - r) * h  # Blender pixel rows run bottom-up
    canvas[y0:y0 + h, c * w:c * w + w] = px
sheet = bpy.data.images.new("sheet", cols * w, rows * h, alpha=False)
sheet.pixels = canvas.ravel()
sheet.filepath_raw = out
sheet.file_format = "PNG"
sheet.save()
print("[sheet]", out, f"{len(imgs)} tiles")
