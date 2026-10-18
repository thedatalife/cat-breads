#!/usr/bin/env python3
"""Check the rendered demo against the spec: streams, a frame per scene, and where the sound is.

    python3 demo/verify.py renders/demo/cat-breads-mcp.mp4 [sheet.png]
"""
import json, os, re, subprocess, sys

mp4 = sys.argv[1]
sheet = sys.argv[2] if len(sys.argv) > 2 else None
spec = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'spec.json')))
LEAD = 0.5

info = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,codec_name,width,height,r_frame_rate',
                       '-of', 'csv=p=0', mp4], capture_output=True, text=True, check=True).stdout.strip().replace('\n', ' | ')
print('streams:', info)

def lufs(start, dur):
    err = subprocess.run(['ffmpeg', '-v', 'info', '-ss', '%.3f' % start, '-t', '%.3f' % dur, '-i', mp4, '-af', 'ebur128', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', err)
    return float(m[-1]) if m else float('nan')

starts, t = [], 0.0
for s in spec['scenes']:
    starts.append(t); t += s['durationSec']
print('scenes: ' + '  '.join('%d@%.1f' % (i, st) for i, st in enumerate(starts)) + '  end@%.1f' % t)

print('-- quiet before the sound comes in (expect < -45 LUFS outside narration)')
print('   intro 0.0-2.8 s: %.1f LUFS' % lufs(0, 2.8))
for i in (1, 2, 3, 4):
    st = starts[i]; print('   scene %d first 0.4 s: %.1f LUFS' % (i, lufs(st, 0.4)))
print('-- narration windows (expect about -18 to -14 LUFS)')
for n in spec['narration']:
    st = starts[n['sceneIndex']] + LEAD
    print('   scene %d  %.1f-%.1f s: %.1f LUFS  "%s…"' % (n['sceneIndex'], st, st + n['durationSec'], lufs(st, n['durationSec']), n['text'][:38]))
print('-- cat voices: the 1.2 s window at each cue versus the 1 s before it')
for i, s in enumerate(spec['scenes']):
    for c in s.get('audioCues', []):
        at = starts[i] + c['atSec']
        print('   scene %d %-14s at %.2f s: %.1f LUFS (before: %.1f)' % (i, os.path.basename(c['src']), at, lufs(at, 1.2), lufs(max(0, at - 1.0), 1.0)))
print('-- music: 1.5 s before musicStartSec vs 3 s after it, and the outro tail')
ms = spec['musicStartSec']
print('   before %.1f LUFS, after %.1f LUFS, outro tail %.1f LUFS' % (lufs(max(0, ms - 1.5), 1.5), lufs(ms + 0.5, 3.0), lufs(t - 1.6, 1.4)))

if sheet:
    mids = [st + s['durationSec'] * (0.6 if s['kind'] in ('capture', 'terminal') else 0.5) for st, s in zip(starts, spec['scenes'])]
    sel = '+'.join("between(t\\,%.3f\\,%.3f)" % (m, m + 0.034) for m in mids)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', mp4, '-vf', "select='%s',scale=880:-1,tile=2x4" % sel, '-frames:v', '1', sheet], check=True)
    print('sheet:', sheet, 'midpoints', [round(m, 1) for m in mids])
