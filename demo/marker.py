#!/usr/bin/env python3
"""Find the white marker frame the lounge's demo mode flashes at t = 0 and print where the clip should start.

    python3 demo/marker.py clip.webm [pad_seconds]

Prints {"markerSec": ..., "mediaStartSec": ...}: the first frame whose average luma exceeds 200 is the marker;
mediaStartSec = markerSec + pad (default 0.15 s) trims it out. A demo-log event at t seconds after the marker then
lands at t - pad seconds into the trimmed clip.
"""
import json, subprocess, sys

clip = sys.argv[1]
pad = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15
out = subprocess.run(['ffprobe', '-v', 'error', '-f', 'lavfi', '-i', 'movie=%s,signalstats' % clip,
                      '-show_entries', 'frame=pts_time:frame_tags=lavfi.signalstats.YAVG', '-of', 'csv=p=0'],
                     capture_output=True, text=True, check=True).stdout
marker = None
for line in out.splitlines():
    parts = line.split(',')
    if len(parts) < 2:
        continue
    try:
        t, y = float(parts[0]), float(parts[1])
    except ValueError:
        continue
    if y > 200:
        marker = t
        break
if marker is None:
    sys.exit('no marker frame found (average luma never exceeded 200)')
print(json.dumps({'markerSec': round(marker, 3), 'mediaStartSec': round(marker + pad, 3)}))
