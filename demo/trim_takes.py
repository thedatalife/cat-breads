#!/usr/bin/env python3
"""Trim the picked Chatterbox takes to their speech, fade the edges and level every line, writing the narration mp3s.

    python3 demo/trim_takes.py [takes_dir] [out_dir]

Reads demo/picks.json: {"L01": {"file": "L01b.flac", "speech_from": 0.22, "speech_to": 3.76}, ...} (the bounds come from the
voice skill's check_takes.py). Keeps 30 ms before and 60 ms after the speech, fades 8 ms in and 40 ms out, and levels each
line to the same integrated loudness so the lines sit evenly in the mix.
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
takes = sys.argv[1] if len(sys.argv) > 1 else '/Users/miles/Code/remotion/public/audio/cat-breads-mcp/takes'
out = sys.argv[2] if len(sys.argv) > 2 else '/Users/miles/Code/remotion/public/audio/cat-breads-mcp'
TARGET = -18.0   # LUFS per line; peaks held at -3 dBFS so the mix has headroom for music and cues

def loudness(args):
    err = subprocess.run(['ffmpeg', '-v', 'info'] + args + ['-af', 'ebur128=peak=true', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', err)[-1])

picks = json.load(open(os.path.join(HERE, 'picks.json')))
for lid, p in sorted(picks.items()):
    src = os.path.join(takes, p['file'])
    start = max(0.0, p['speech_from'] - 0.03)
    dur = p['speech_to'] + 0.06 - start
    I = loudness(['-ss', '%.3f' % start, '-t', '%.3f' % dur, '-i', src])
    gain = TARGET - I
    af = 'afade=t=in:st=0:d=0.008,afade=t=out:st=%.3f:d=0.04,volume=%.2fdB,alimiter=limit=0.708:attack=3:release=60:level=false' % (dur - 0.04, gain)
    dest = os.path.join(out, lid + '.mp3')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', '%.3f' % start, '-t', '%.3f' % dur, '-i', src, '-af', af,
                    '-ar', '44100', '-codec:a', 'libmp3lame', '-q:a', '2', dest], check=True)
    print('%s  %-9s %5.2f s  measured %6.1f LUFS  gain %+5.1f dB  -> %s' % (lid, p['file'], dur, I, gain, os.path.basename(dest)))
