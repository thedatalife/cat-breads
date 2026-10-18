#!/bin/sh
# Landscape crops for the demo's still beats, at 2.128:1 (the studio frame's content box).
# Usage: demo/crops.sh [out_dir]   (default: the Demo Studio's public/captures/cat-breads-mcp)
set -e
cd "$(dirname "$0")/.."
OUT=${1:-/Users/miles/Code/remotion/public/captures/cat-breads-mcp}
mkdir -p "$OUT"
ffmpeg -y -v error -i renders/gallery.png -vf "crop=2800:1316:0:42" "$OUT/sdf_gallery.png"                 # the four SDF studies
ffmpeg -y -v error -i web/cards_photo.jpg -vf "crop=1050:493:0:55" -q:v 2 "$OUT/cards_photo.jpg"             # Lane's cards, rows 1-2
ffmpeg -y -v error -i renders/cards/cat_breads_cards.jpg -vf "crop=2426:1450:0:20,pad=3086:1450:330:0:0x804f26" -q:v 2 "$OUT/cards_render.jpg"   # the renders, rows 1-2, padded with the table colour so the grid sits like the photo
echo "wrote $OUT"
