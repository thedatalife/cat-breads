#!/bin/zsh
# Derive every icon size from web/icons/icon-1024.png (rendered by export_icon.py) with macOS sips, plus a PNG-in-ICO favicon.
set -e
cd "$(dirname "$0")/web"
sips -z 180 180 icons/icon-1024.png --out apple-touch-icon.png >/dev/null
sips -z 192 192 icons/icon-1024.png --out icons/icon-192.png >/dev/null
sips -z 512 512 icons/icon-1024.png --out icons/icon-512.png >/dev/null
sips -z 64 64 icons/icon-1024.png --out favicon-64.png >/dev/null
sips -z 32 32 icons/icon-1024.png --out favicon-32.png >/dev/null
sips -z 16 16 icons/icon-1024.png --out /tmp/cb-favicon-16.png >/dev/null
sips -z 48 48 icons/icon-1024.png --out /tmp/cb-favicon-48.png >/dev/null
python3 - <<'PY'
import struct
sizes = [(16, '/tmp/cb-favicon-16.png'), (32, 'favicon-32.png'), (48, '/tmp/cb-favicon-48.png')]
blobs = [open(p, 'rb').read() for _, p in sizes]
offset = 6 + 16 * len(sizes)
out = struct.pack('<HHH', 0, 1, len(sizes))
for (n, _), b in zip(sizes, blobs):
    out += struct.pack('<BBBBHHII', n, n, 0, 0, 1, 32, len(b), offset)
    offset += len(b)
open('favicon.ico', 'wb').write(out + b''.join(blobs))
PY
rm -f /tmp/cb-favicon-16.png /tmp/cb-favicon-48.png
ls -la apple-touch-icon.png favicon-32.png favicon-64.png favicon.ico icons/
