# Demo video: an SDF experiment becomes Lane's playground, voiced through the Comfy Cloud MCP

## Context

This repo started as an exploration of modelling with signed distance fields in Blender (`sdf.py`, the pod / gyroid egg / linked rings studies in `renders/gallery.png`). Then Miles's daughter Lane drew 23 "Cat Breads" on index cards (`web/cards_photo.jpg`), the experiment had its subject, and with Claude Code every card became an SDF cat that moved into a Three.js lounge built for her iPad (`web/`, live at cat-breads-lounge.vercel.app, with a "For Lane" sign over the couch). The lounge was finished and silent until it needed sound, and the **Comfy Cloud MCP** made that fast: from the coding session Claude called ElevenLabs sound generation once per cat (23 voices, 1.5 s each) and ACE-Step for the ambient loop. The video tells that story in Miles's own cloned voice and showcases the MCP as the thing that gave the playground its sound.

Decisions already made (with Miles):
- Pipeline: **Comfy Demo Studio** (`/Users/miles/Code/remotion`: Remotion + Playwright + Nodey, 1920x1080 mp4), dark node-canvas theme.
- Narration: **Miles's cloned voice** via the `miles-voiceover` skill (Chatterbox on Comfy Cloud, his nine mood reference clips, saved workflow `07e8a9f3-4821-459b-bf7b-ada05c458a65`; GPU time only, no partner credits, no new recording). First person. Lane appears as her cards and her first name only.
- Credits OK up to ~150; expected spend ≈ 5 (a few ElevenLabs sound-effect runs on camera ≈ 1 each). Music bed reuses the existing ACE-Step loop.
- Length: the story grew to eight beats, so the cut lands at **about 55 s** (the 50 s target would need one beat merged; flagged for Miles).
- Storyboard approved at https://claude.ai/artifact/DyokRgGDAZnrqce9o6ZX7e (kept in sync with this plan).

Findings that shape the plan:
- The studio's default headless browser renders the lounge at **<1 fps** (SwiftShader). Full Chromium with `channel: "chromium"` + `--use-angle=metal --ignore-gpu-blocklist` runs it at **~120 fps** (probed). `capture/capture.ts` hardcodes `chromium.launch()` and DPR 2, so it needs launch options.
- Playwright clips are **silent**, and `DemoSpec` only has one narration clip per scene plus a looping music bed at 0.18 from frame 0. The video needs cat voices at exact moments and music that starts mid-video (when the ACE-Step call "completes"), so the spec gets an additive `audioCues` layer, `mediaStartSec` trim, `musicStartSec`, volume and ducking.
- The MCP session is a **terminal replay scene rendered in Remotion** (new `kind: "terminal"`): crisp, deterministic, timed to the narration, styled like a Claude Code session with the Comfy lime accent on MCP lines. Its content comes from a real `partner_generate` call run during implementation so the request and response shapes are genuine.
- Sync for the voices clip: a scripted demo mode in the lounge flashes a white marker frame, presses cats on a schedule and logs each event relative to the marker; ffmpeg `signalstats` finds the marker in the clip; the marker is trimmed out with `mediaStartSec`.
- `window.lounge` already exposes `play(name, move)`, `meow(name)`, `cats`, `camera`, `controls`, `pointer` (web/main.js:1311); the demo mode reuses `play`/`meow`.

## Storyboard (~55 s, 30 fps; capture scenes take their length from the measured narration + 0.5 s lead + 0.8 s tail)

| # | Scene | ~Length | Picture | Sound |
|---|-------|---------|---------|-------|
| 0 | Intro | 3 s | "Cat Breads" / "An SDF experiment that became Lane's playground. Voiced through the Comfy Cloud MCP." Nodey waves | silence |
| 1 | The experiment (still, Ken Burns) | 6 s | `renders/gallery.png`: the pod, the gyroid egg, the linked rings, the lattice ball, drifting left to right | narration 1 |
| 2 | Her cards (still, Ken Burns) | 7.5 s | landscape crop of `web/cards_photo.jpg` | narration 2 |
| 3 | The build (still) | 7.5 s | the same rows of `renders/cards/cat_breads_cards.jpg`, cropped identically so the cut lands as a match | narration 3 |
| 4 | The lounge (video) | 6 s | slow dolly-in on the finished room, "For Lane" sign in frame, cats idling | narration 4; the room is silent |
| 5 | MCP session (terminal replay) | 12 s | user prompt, `comfyui-cloud · partner_generate` lines for the Lucky Cat bell, Bumble Cat buzz, Explorer echo with results arriving, then the ACE-Step `run_template`; callout "Comfy Cloud MCP" on the first tool line, Nodey points | narration 5; a bell cue when the first result lands; **music fades in the moment the ACE-Step line completes** |
| 6 | Voices (video) | 10 s | cats pressed in order (Lucky Cat, Bumble Cat, Explorer, Devil Cat, Unimeow, Mascot); the room looks at each one | narration 6, then each cat's mp3 as a cue at its press time; music ducked |
| 7 | Outro | 5 s | "Built with Claude Code. Voiced through the Comfy Cloud MCP." / cloud.comfy.org, small "for Lane", Nodey celebrates | narration 7, music up |

Narration, first person, with the `miles-voiceover` mood per line (wording trimmed to the measured takes):
1. natural: "This started as an experiment: modelling with signed distance fields in Blender."
2. amused: "Then my daughter Lane drew twenty-three cats on index cards, and the experiment had its subject."
3. natural: "With Claude Code, each card became a cat: the Lucky Cat, the Bumble Cat, the Show Off."
4. quiet: "It grew into a playground for her iPad. Finished, and completely silent."
5. calm: "So I asked for sound. With the Comfy Cloud MCP, Claude called ElevenLabs for a voice per cat and ACE-Step for the music, without leaving the editor."
6. excited: "Tap a cat, and it answers."
7. confident: "Even this narration is my voice, cloned through the MCP."

Terminal replay content (scene 5), quoting a real call made in step 3:
```
> The lounge needs sound. Give every cat a 1.5 s voice that fits its card, and a loop of lounge music, through Comfy Cloud.
⏺ comfyui-cloud · partner_generate  type "audio" · model "elevenlabs/sound-generation"
    prompt "a small brass bell jingling twice, cute, close" · duration 1.5
  ⎿ submitted → completed · saved to the asset library · /api/s/<real short id>
⏺ comfyui-cloud · partner_generate  prompt "a fat bumblebee buzzing past, cartoonish" · duration 1.5
⏺ comfyui-cloud · partner_generate  prompt "a bubbly underwater echo, playful" · duration 1.5
  … 20 more voices
⏺ comfyui-cloud · run_template  audio_ace_step_1_5_checkpoint · "warm lo-fi lounge, soft keys, brushed drums" · 60 s
  ⎿ completed · ambient.flac
⏺ bash  ffmpeg … silenceremove, loudnorm → web/audio/<Name>.mp3 ×23, ambient.mp3
```

## Files

This repo (worktree):
- `web/main.js` — demo mode (new block near the `window.lounge` export, ~80 lines).
- `demo/spec.json` — the DemoSpec (re-renderable); `demo/capture-lounge.json`, `demo/capture-voices.json` — Playwright flows; `demo/lines.json` — the narration lines with moods (the voice skill's input); `demo/narration.md` — script, picks and the terminal transcript; `demo/marker.py` — flash-frame finder; `demo/crops.sh` — the matching landscape crops; `README.md` — short "Demo video" section.
- `renders/demo/cat-breads-mcp.mp4` — the output (size checked before deciding whether it is committed).

Comfy Demo Studio (`/Users/miles/Code/remotion`), all additive with defaults so `create_demo` keeps working:
- `capture/capture.ts`, `src/schema/DemoSpec.ts`, `src/timeline.ts`, `src/ProductDemo.tsx`, `src/scenes/CaptureScene.tsx`, new `src/scenes/TerminalScene.tsx`, `mcp/server.ts`, `README.md`.

## Steps

### 1. Lounge demo mode (`web/main.js`)
- Parse `location.search`: `demo=lounge` or `demo=voices`, optional `at=LuckyCat:3.4,BumbleCat:4.8,...` (press schedule in seconds after the marker; defaults in code).
- In demo mode: hide `#mute`, skip audio start, wait until `cats.length === names.length`, settle 1 s, then show a fixed full-screen white `div` for 120 ms, record `t0 = performance.now()`, log `{type:"marker", t:0}`.
- Drive from the existing `frame()` loop by elapsed time: `lounge` = slow dolly-in (camera distance eased from +6 units to the fitted distance over ~8 s with a slight yaw sweep, via `camera.position` + `controls.update()`, keeping the sign in frame); `voices` = at each scheduled time set `pointer` toward the cat's projected screen position so the room looks at it, call `play(cat)` and `meow(cat)`, log `{type:"meow", name, t}`.
- Expose `window.lounge.demo = { log, done }`; `done` flips ~2 s after the last event (or at 9 s for `lounge`). No behaviour change without `?demo`.

### 2. Demo Studio extension (`/Users/miles/Code/remotion`)
- `capture/capture.ts`: `CaptureRequest.launch?: { channel?, args?, headless? }` and `deviceScaleFactor?` (default 2) passed to `chromium.launch` and all three `newContext` calls. New steps `{action:"waitForFunction", expression, timeoutMs?}` and `{action:"evaluate", expression, name}` whose JSON result goes into `manifest.json` under `results[name]` and the return value (`{ assets, results }`; update both call sites in `mcp/server.ts`).
- `src/schema/DemoSpec.ts`: `CaptureScene.mediaStartSec` (default 0), `CaptureScene.audioCues: [{ src, atSec, volume? }]` (default []); new `TerminalScene` (`kind: "terminal"`, `title`, `lines: [{ role: "user"|"tool"|"result"|"note", text, atSec }]`, `caption`, `callouts`, `nodey`, `durationSec`, `audioCues`); `DemoSpec.musicStartSec` (default 0), `musicVolume` (default 0.18), `musicDuck` (volume under narration, optional).
- `src/scenes/TerminalScene.tsx`: dot-grid background, dark window with traffic lights and title, monospace lines appearing at `atSec` (short typewriter for user lines, fade for tool/result lines), lime accent on `comfyui-cloud` tool lines, blinking cursor; reuses `Callout`, `Caption`, `NodeyHost` like `CaptureScene`.
- `src/scenes/CaptureScene.tsx`: `OffthreadVideo startFrom={round(mediaStartSec*fps)}`, `muted`.
- `src/timeline.ts`: handle the terminal kind, add `narrationEndFrame`.
- `src/ProductDemo.tsx`: render `TerminalScene`; each cue as `<Sequence from={sceneStart + atSec*fps}><Audio/></Sequence>`; music inside `<Sequence from={musicStartSec*fps}>` with a 1.5 s fade-in and a frame-based `volume` that drops to `musicDuck` inside narration ranges.
- `mcp/server.ts`: expose `launch` / `deviceScaleFactor` on `capture_surface`; mention the new steps. `pnpm typecheck`.
- Everything runs through the CLI (`pnpm capture '<json>'`, `pnpm tsx scripts/render-spec.ts`), so the running MCP server copy needs no restart.

### 3. Comfy Cloud generations (through the MCP)
- Transcript source: load `partner_generate` and run the Lucky Cat bell for real (`type: "audio"`, `model: "elevenlabs/sound-generation"`, 1.5 s; ≈1 credit) to capture the genuine request/response shape; optionally the Bumble Cat and Explorer prompts too. The lounge keeps its existing voices.
- Narration, per the `miles-voiceover` skill: write `demo/lines.json` (seven lines with the moods above, `max_seconds` per slot); `build_graph.py lines.json --takes 3 --prefix catbreads` → `submit_workflow`; `wait_for_job` → `get_output` (paged) → download takes as `<id><letter>.flac` into `~/Code/remotion/public/audio/cat-breads-mcp/takes/`; `check_takes.py` (Whisper) picks a take per line; trim each pick to its speech (~30 ms before, ~60 ms after), fade 8 ms in / 40 ms out, level every line to the same active-speech loudness; play line 1 to Miles before committing the rest. If a take runs long for its slot, `atempo` up to 1.1.
- Copy `web/audio/ambient.mp3` and the pressed cats' mp3s into `~/Code/remotion/public/audio/cat-breads-mcp/` (Remotion serves only from `public/`).

### 4. Captures (`pnpm capture`, lounge served by the `lounge` launch config on :8765)
- Both lounge flows: `launch: {channel:"chromium", args:["--use-angle=metal","--ignore-gpu-blocklist"]}`, `deviceScaleFactor: 1`, viewport **1720x808** (the browser frame's content box, so nothing is cropped; fall back to 1600x900 if the wide room reads too small). Steps: `startVideo` → `goto ?demo=lounge|voices&at=...` → `waitForFunction window.lounge?.demo?.done` → `evaluate window.lounge.demo.log` → `stopVideo`.
- Stills: `demo/crops.sh` cuts matching landscape regions (same rows, ~2.1:1) from `web/cards_photo.jpg` and `renders/cards/cat_breads_cards.jpg`, and a 2.1:1 strip of `renders/gallery.png`, into `public/captures/cat-breads-mcp/`.
- `demo/marker.py`: `ffprobe -f lavfi "movie=<clip>,signalstats"` → first frame with `YAVG > 200` = `markerSec`; `mediaStartSec = markerSec + 0.15`; each cue `atSec = t_event - 0.15`.

### 5. Assemble and render
- Build `demo/spec.json`: scenes above, terminal lines timed to narration 5, `musicStartSec` = terminal scene start + the ACE-Step completion line's time, `musicVolume: 0.5`, `musicDuck: 0.15` (about 9 dB under the voice, per the voice skill), narration segments with measured `durationSec`, cues from the voices log, Nodey on intro/outro and pointing at the terminal callout.
- `cd ~/Code/remotion && pnpm tsx scripts/render-spec.ts <worktree>/demo/spec.json <worktree>/renders/demo` → `renders/demo/cat-breads-mcp.mp4`.

## Verification
- `ffprobe` the mp4: 1920x1080, 30 fps, ~53–58 s, one AAC audio stream.
- Extract frames at each scene's midpoint with `ffmpeg -ss` and view them: SDF shapes, cards legible and the match cut lining up, cats visible and hopping, no white marker frame, terminal lines legible with the lime MCP accent, callouts and captions readable, Lane's name only where intended.
- Audio placement: `ffmpeg -af volumedetect` over 1 s windows: narration only through scene 4, a level rise at each cue time versus the second before it, music present after `musicStartSec`; the mix mastered near −14 LUFS with the voice about 8 LU above the music.
- `pnpm typecheck` passes in the studio; the lounge still behaves normally without `?demo` (open :8765, press a cat, mute button present).
- Open the mp4 in the browser pane for a final look and send it with SendUserFile.

## Out of scope
- Night-mode beat, Comfy Cloud canvas capture, live 24th-cat generation, a separate iPad beat.
- Word-synced captions (the Whisper check gives rough timings; captions show whole lines).
- Note for publishing: the studio's PP Formula display font is commercial; confirm licensing before external use (brand guidelines).
