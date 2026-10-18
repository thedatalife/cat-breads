#!/usr/bin/env python3
"""Master the rendered demo: two-pass loudnorm to -14 LUFS (true peak -1.5 dBFS), video stream copied.

    python3 demo/master.py renders/demo/cat-breads-mcp.render.mp4 renders/demo/cat-breads-mcp.mp4
"""
import json, re, subprocess, sys

src, dst = sys.argv[1], sys.argv[2]
err = subprocess.run(['ffmpeg', '-v', 'info', '-i', src, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'],
                     capture_output=True, text=True).stderr
m = json.loads(err[err.rfind('{'):err.rfind('}') + 1])
print('measured: I %s LUFS, TP %s dBFS, LRA %s LU, thresh %s' % (m['input_i'], m['input_tp'], m['input_lra'], m['input_thresh']))
af = ('loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true'
      % (m['input_i'], m['input_tp'], m['input_lra'], m['input_thresh'], m['target_offset']))
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-c:v', 'copy', '-af', af, '-ar', '48000', '-c:a', 'aac', '-b:a', '192k',
                '-movflags', '+faststart', dst], check=True)
out = subprocess.run(['ffmpeg', '-v', 'info', '-i', dst, '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
print('mastered:', ' '.join(re.findall(r'(I:\s+-?[\d.]+ LUFS|Peak:\s+-?[\d.]+ dBFS)', out)[-2:]), '->', dst)
