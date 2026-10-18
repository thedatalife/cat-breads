#!/usr/bin/env python3
"""Assemble demo/spec.json (a Comfy Demo Studio DemoSpec) for the Cat Breads MCP video.

    python3 demo/build_spec.py [--studio /Users/miles/Code/remotion]

Inputs (all relative to the studio's public/ unless noted):
  captures/cat-breads-mcp/{sdf_gallery.png,cards_photo.jpg,cards_render.jpg}   demo/crops.sh
  captures/cat-breads-mcp/{lounge,voices}.webm                                  demo/capture-*.json via the studio's capture CLI
  demo/voices-manifest.json (this repo)                                         the capture manifest with the press log
  audio/cat-breads-mcp/L01.mp3 … L07.mp3                                        the trimmed, levelled narration (optional: without
                                                                                them the spec is a silent draft with estimated timings)
  audio/cat-breads-mcp/{ambient,<Cat>}.mp3                                      copied from web/audio
Marker frames are located with demo/marker.py; every press in the log lands at (t - pad) seconds into the trimmed clip.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ap = argparse.ArgumentParser()
ap.add_argument('--studio', default='/Users/miles/Code/remotion')
ap.add_argument('--out', default=os.path.join(HERE, 'spec.json'))
a = ap.parse_args()
PUB = os.path.join(a.studio, 'public')
CAP = 'captures/cat-breads-mcp'
AUD = 'audio/cat-breads-mcp'
PAD = 0.15
LEAD, TAIL = 0.5, 0.8          # the studio's narration pads (src/timeline.ts)

lines = {l['id']: l for l in json.load(open(os.path.join(HERE, 'lines.json')))}

def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)

def narration(idx, lid):
    """A NarrationSegment for scene idx; measured from the trimmed take when it exists, else estimated."""
    seg = {'sceneIndex': idx, 'text': lines[lid].get('caption', lines[lid]['text'])}
    f = os.path.join(PUB, AUD, lid + '.mp3')
    if os.path.exists(f):
        seg['audio'] = '%s/%s.mp3' % (AUD, lid)
        seg['durationSec'] = round(duration(f), 3)
    else:
        words = len(lines[lid]['text'].split())
        seg['durationSec'] = round(max(1.2, words / 2.6), 3)
        seg['_estimated'] = True
    return seg

def marker(clip):
    out = subprocess.run([sys.executable, os.path.join(HERE, 'marker.py'), os.path.join(PUB, CAP, clip), str(PAD)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)

manifest = json.load(open(os.path.join(HERE, 'voices-manifest.json')))
log = manifest['results']['voices-log']
m_lounge, m_voices = marker('lounge.mp4'), marker('voices.mp4')

narr = {1: narration(1, 'L01'), 2: narration(2, 'L02'), 3: narration(3, 'L03'), 4: narration(4, 'L04'),
        5: narration(5, 'L05'), 6: narration(6, 'L06'), 7: narration(7, 'L07')}
def beat(idx):  # a narrated scene's length: the studio's lead + speech + tail
    return round(LEAD + narr[idx]['durationSec'] + TAIL, 3)

# --- the MCP session, timed to narration 5 (12.5 s floor so the lines have room) ---------------------------------
term_lines = [
    {'role': 'user', 'atSec': 0.3, 'text': 'The lounge needs sound. Give every cat a 1.5 s voice that fits its card, and a loop of lounge music, through Comfy Cloud.'},
    {'role': 'tool', 'atSec': 3.2, 'text': 'comfyui-cloud · partner_generate  type "audio" · model "elevenlabs/sound-generation" · prompt "a small brass bell jingling twice, cute, close" · duration 1.5'},
    {'role': 'result', 'atSec': 4.4, 'text': 'submitted → completed in 8 s · 4dd389b5 · saved to the asset library with its graph'},
    {'role': 'tool', 'atSec': 5.3, 'text': 'comfyui-cloud · partner_generate  prompt "a fat bumblebee buzzing past, cartoonish" · duration 1.5'},
    {'role': 'tool', 'atSec': 6.1, 'text': 'comfyui-cloud · partner_generate  prompt "a bubbly underwater echo, playful" · duration 1.5'},
    {'role': 'note', 'atSec': 6.9, 'text': '… 20 more voices, one call each'},
    {'role': 'tool', 'atSec': 7.8, 'text': 'comfyui-cloud · run_template  audio_ace_step_1_5_checkpoint · "warm lo-fi lounge, soft keys, brushed drums" · 60 s'},
    {'role': 'result', 'atSec': 9.0, 'text': 'completed · ambient.flac · 60 s loop'},
    {'role': 'note', 'atSec': 9.9, 'text': '⏺ bash  ffmpeg … silenceremove, loudnorm → web/audio/<Name>.mp3 ×23, ambient.mp3'},
]
MUSIC_LINE_AT = 9.0
term_len = max(12.5, beat(5))

scenes = [
    {'kind': 'intro', 'title': 'Cat Breads',
     'subtitle': "An SDF experiment that became Lane's playground. Voiced through the Comfy Cloud MCP.",
     'mascot': True, 'durationSec': 3},
    {'kind': 'capture', 'media': '%s/sdf_gallery.png' % CAP, 'mediaType': 'image', 'surface': 'none',
     'caption': lines['L01']['text'], 'camera': {'fromScale': 1.0, 'toScale': 1.1, 'focusX': 0.5, 'focusY': 0.55},
     'durationSec': beat(1)},
    {'kind': 'capture', 'media': '%s/cards_photo.jpg' % CAP, 'mediaType': 'image', 'surface': 'none',
     'caption': lines['L02']['text'], 'camera': {'fromScale': 1.0, 'toScale': 1.12, 'focusX': 0.7, 'focusY': 0.72},
     'durationSec': beat(2)},
    {'kind': 'capture', 'media': '%s/cards_render.jpg' % CAP, 'mediaType': 'image', 'surface': 'none',
     'caption': lines['L03']['text'], 'camera': {'fromScale': 1.06, 'toScale': 1.0, 'focusX': 0.7, 'focusY': 0.72},
     'durationSec': beat(3)},
    {'kind': 'capture', 'media': '%s/lounge.mp4' % CAP, 'mediaType': 'video', 'mediaStartSec': m_lounge['mediaStartSec'],
     'surface': 'web', 'url': 'cat-breads-lounge.vercel.app', 'caption': lines['L04']['text'], 'durationSec': beat(4)},
    {'kind': 'terminal', 'title': 'claude · ~/Code/blndr', 'badge': 'Claude Code · Comfy Cloud MCP', 'lines': term_lines,
     'caption': lines['L05'].get('caption', lines['L05']['text']),
     'nodey': {'point': {'x': 0.077, 'y': 0.288}},   # Nodey points at the first MCP call's bullet
     'audioCues': [{'src': '%s/LuckyCat.mp3' % AUD, 'atSec': 4.45, 'volume': 0.6}],
     'durationSec': term_len},
    {'kind': 'capture', 'media': '%s/voices.mp4' % CAP, 'mediaType': 'video', 'mediaStartSec': m_voices['mediaStartSec'],
     'surface': 'web', 'url': 'cat-breads-lounge.vercel.app', 'caption': lines['L06']['text'],
     'audioCues': [{'src': '%s/%s.mp3' % (AUD, e['name']), 'atSec': round(e['t'] - PAD, 3), 'volume': 0.9}
                   for e in log if e['type'] == 'meow'],
     'durationSec': 11},
    {'kind': 'outro', 'headline': 'Built with Claude Code.\nVoiced through the Comfy Cloud MCP.',
     'cta': 'Try the Comfy Cloud MCP', 'url': 'cloud.comfy.org  ·  for Lane', 'mascot': True,
     'durationSec': max(5.5, beat(7))},
]

# music starts the moment the ACE-Step line completes
start5 = sum(s['durationSec'] for s in scenes[:5])
spec = {
    'id': 'cat-breads-mcp', 'title': 'Cat Breads: voiced through the Comfy Cloud MCP', 'theme': 'dark',
    'assetDir': '.', 'fps': 30, 'width': 1920, 'height': 1080,
    'music': '%s/ambient.mp3' % AUD, 'musicStartSec': round(start5 + MUSIC_LINE_AT, 3),
    'musicVolume': 0.6, 'musicDuck': 0.25, 'musicFadeSec': 2.0,
    'scenes': scenes,
    'narration': [narr[i] for i in sorted(narr)],
}
json.dump(spec, open(a.out, 'w'), indent=1, ensure_ascii=False)
total = sum(s['durationSec'] for s in scenes)
est = [i for i in narr if narr[i].get('_estimated')]
print('wrote %s: %d scenes, %.1f s total, music at %.1f s, markers lounge %.2f voices %.2f%s' % (
    a.out, len(scenes), total, spec['musicStartSec'], m_lounge['markerSec'], m_voices['markerSec'],
    ', ESTIMATED narration for lines %s' % est if est else ''))
