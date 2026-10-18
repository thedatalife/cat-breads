# Narration and session transcript for the demo video

The narration is Miles's voice, cloned with Chatterbox on Comfy Cloud through the `miles-voiceover` skill: every line was
generated three times against a mood reference clip (one Comfy Cloud job, `demo/voice_graph.json`, GPU time only), checked
with Whisper (`check_takes.py`), and the tightest clean take was trimmed to its speech, faded and levelled to about -18 LUFS
with a -3 dBFS ceiling (`demo/trim_takes.py`, bounds in `demo/picks.json`).

| Line | Mood | Take | Speech | Text |
|---|---|---|---|---|
| L01 | natural | L01b | 3.6 s | This started as an experiment: modelling with signed distance fields in Blender. |
| L02 | amused | L02c | 4.7 s | Then my daughter Lane drew twenty-three cats on index cards, and the experiment had its subject. |
| L03 | natural | L03c | 4.3 s | With Claude Code, each card became a cat: the Lucky Cat, the Bumble Cat, the Show Off. |
| L04 | quiet | L04b | 4.9 s | It grew into a playground for her iPad. Finished, and completely silent. |
| L05 | calm | L05b (retake) | 7.8 s | So I asked for sound. With the Comfy Cloud MCP, Claude called ElevenLabs for a voice per cat and Ace Step for the music, without leaving the editor. (spoken as two words: the hyphen made the clone pause; the caption keeps "ACE-Step") |
| L06 | excited | L06a | 1.9 s | Tap a cat, and it answers. |
| L07 | confident | L07c | 3.5 s | Even this narration is my voice, cloned through the MCP. |

Whisper flagged L01, L02 and L05 only for spelling ("modeling", "23", "Eleven Labs", "ace stepped"); the takes read the
script. If a line needs a retake, regenerate it with new seeds (`seeds` in `demo/lines.json`) and re-run the trim.

## The session replayed in beat 5

The terminal scene quotes a real call made while building the video (ElevenLabs sound generation through the Comfy Cloud
MCP, prompt_id `4dd389b5-daf0-4967-87b2-1c3ac2751c06`, about one credit). The lounge keeps its original voices.

```
> The lounge needs sound. Give every cat a 1.5 s voice that fits its card, and a loop of lounge music, through Comfy Cloud.
⏺ comfyui-cloud · partner_generate  type "audio" · model "elevenlabs/sound-generation" · prompt "a small brass bell jingling twice, cute, close" · duration 1.5
  ⎿ submitted → completed in 8 s · 4dd389b5 · saved to the asset library with its graph
⏺ comfyui-cloud · partner_generate  prompt "a fat bumblebee buzzing past, cartoonish" · duration 1.5
⏺ comfyui-cloud · partner_generate  prompt "a bubbly underwater echo, playful" · duration 1.5
  … 20 more voices, one call each
⏺ comfyui-cloud · run_template  audio_ace_step_1_5_checkpoint · "warm lo-fi lounge, soft keys, brushed drums" · 60 s
  ⎿ completed · ambient.flac · 60 s loop
⏺ bash  ffmpeg … silenceremove, loudnorm → web/audio/<Name>.mp3 ×23, ambient.mp3
```

The music bed is the lounge's own `web/audio/ambient.mp3` (ACE-Step 1.5); it starts the moment the ACE-Step line completes.
