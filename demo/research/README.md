# Research notes from the demo build

Findings that shaped the video, kept here so they are not lost with the session that found them.

## WebGL capture speed (`probe-webgl-fps.mjs`)

Playwright's default headless shell renders the lounge through SwiftShader at 0.7 to 1 fps, so a recording of it is a
slideshow. The full Chromium build with `--use-angle=metal --ignore-gpu-blocklist` uses the GPU and runs the same scene at
about 120 fps, headed or headless. The Demo Studio's `launch` option exists because of this probe.

## Sync without audio

Playwright clips carry no audio. The lounge's demo mode flashes a white frame when its schedule starts and logs each
press against it; `marker.py` finds the frame by average luma (first frame above 200) and the trimmed clip starts
0.15 s after it, so a press logged at t seconds lands at t minus 0.15 s into the clip. Presses fired within 6 ms of
their schedule in every capture.

## Clips and the bundle server

VP8 webm from Playwright has sparse keyframes, so Remotion's frame extraction decodes from the start for every frame and
the bundle server starves: a late render tab timed out loading fonts after 28 s. Transcoding the clips to H.264 with a
keyframe every 15 frames fixed it; marker times moved by at most 13 ms.

## The narration

Seven lines, three takes each, from Miles's Chatterbox clone on Comfy Cloud (one job, GPU time only). Whisper flagged
only spelling ("modeling", "23", "Eleven Labs"). Writing "ACE-Step" with the hyphen made the clone pause between the
words; "Ace Step" as two words reads naturally and Whisper hears it as one unit. Levelling: -18 LUFS per line with a
-3 dBFS ceiling (`alimiter` with `level=false`; the default auto-level pushes the signal back up), music at 0.6 fading
in over 2 s and ducked to 0.25 under speech, the mix mastered to -14 LUFS.

## Comfy Cloud

The lounge's voices are `partner_generate` calls to `elevenlabs/sound-generation` (1.5 s each, about one credit each);
the loop is ACE-Step 1.5 because YuE2's checkpoint is not deployed on the Cloud workers. The transcript in the video
quotes a real call made during the build, prompt_id `4dd389b5-daf0-4967-87b2-1c3ac2751c06`.

## Where the run's assets are

`demo/assets/captures/` holds the two Playwright clips the video uses, `demo/assets/narration/` the seven trimmed lines
and every raw take, `demo/storyboard/` the review page Miles approved, and `demo/plan.md` the implementation plan.
