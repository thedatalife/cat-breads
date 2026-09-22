# blndr — signed distance fields in Blender 5.2

Two ways to model organic shapes with SDFs, both verified against the Blender 5.2.1 LTS build on this Mac.

## Route A: numpy SDFs (unlimited math)

`sdf.py` is a small vectorised toolkit: primitives (sphere, box, ellipsoid, torus, capsule,
cone capsule, cylinder, plane), TPMS lattices (gyroid, Schwarz P/D), smooth booleans, shells,
domain operators (twist, bend, repeat, mirror, noise warp) and Perlin/fBm noise. `sdf.mesh()`
samples a function on a grid and extracts the surface with the OpenVDB module that ships inside
Blender's Python, so there is nothing to install.

`shapes.py` holds three studies: `pod`, `gyroid_egg`, `linked_rings`.

```bash
blender -b --python render.py                       # mesh, light, render everything, save sdf_shapes.blend
blender -b --python render.py -- --quick            # 64^3 grid, 16 samples; writes renders/quick/ and sdf_shapes_quick.blend
blender -b --python render.py -- --only Pod --res 256
```

Writing a new shape is one function from points to distances:

```python
def blob(p):
    q = sdf.warp(p, amplitude=0.1, frequency=2.0)          # organic wobble
    d = sdf.smooth_union(sdf.sphere(q, 0.6), sdf.torus(q, 0.7, 0.2), 0.2)
    return sdf.intersect(d, sdf.gyroid(p, scale=10, thickness=0.07))
```

Inside a live Blender session (the Python console, or the Blender MCP `execute_blender_code` tool):

```python
import sys; sys.path.insert(0, "/Users/miles/Code/blndr")
import sdf, shapes
sdf.add_object("Blob", blob, bounds=(-1.3, 1.3), res=200)
```

## Route B: native geometry nodes (live sliders)

`nodes_sdf.py` builds the same idea purely from Blender 5.2's grid nodes: Position -> Math ->
Field to Grid -> Grid to Mesh -> Mesh to SDF Grid -> SDF Grid Fillet -> Grid to Mesh. Every
parameter (resolution, blob radius, wobble, gyroid scale/thickness, voxel size, fillet, adaptivity)
is a slider on the modifier. Gotcha discovered on the way: Field to Grid outputs a generic float
grid, and the SDF-only nodes (Fillet, Offset, Boolean) reject it until it has been round-tripped
through Mesh to SDF Grid (or built with Points to SDF Grid). Second gotcha: Grid to Mesh's
Threshold defaults to 0.1, not 0, which silently misses a narrow-band level set. Set it to 0.

## Files

- `sdf_shapes.blend` — all four objects in a row with lights and camera; open it in Blender 5.2.
- `renders/` — Cycles renders of each shape and a gallery.

## Characters: the "Cat Breads" cards

`cats.py` layers a small character kit on top: a `Model` is a smooth union of *coloured* SDF parts
plus paint layers (discs, strokes, stripe bands, noise patches, arcs for happy/closed/x eyes). The
colour at every mesh vertex is the softmin-weighted colour of the nearest parts with the paint
layers composited on top, and the runner bakes it into a vertex-colour attribute, so patches,
stripes, eyes and mouths need no UVs or textures. `Cat` builds a loaf body and places ears, paws,
a tail, whiskers and a face on the head surface; props (boxes, a fishbowl, a sandwich, a heart, a
briefcase, a snowman) are extra parts with their own bounds and materials.

All 23 cards are modelled: Mascot, Siamese, Sphynx, Norwegian Forest, Catuccino, Wanderer, Day Cat,
Investigator One, Lucky Cat, Explorer, Dozer, Stretcher, Show Off, Box Tester, Nature Lover,
Large Hearted, Kitty Roll, Angel Cat, Devil Cat, Unimeow, Bumble Cat, Holiday Kitty, Accountcat.

```bash
blender -b --python render_cats.py                  # renders/cats/<Name>.png, hangout.png, cat_breads.blend
blender -b --python render_cats.py -- --quick       # seconds; writes renders/cats/quick/ and cat_breads_quick.blend
blender -b --python render_cats.py -- --only DevilCat --no-scene
blender -b --python render_cats.py -- --no-individual          # just the group scene
blender -b --python contact_sheet.py -- renders/cats/quick sheet.png 6   # tile the per-cat renders
```

`hangout_layout()` in cats.py arranges everyone in three loosely curved rows with a little jitter and
yaw so the group reads as a crowd; `cat_breads.blend` opens on that scene with lights and camera.

The studio in render_cats.py is a curved sweep (floor bending up into a wall) carrying a cream-to-
terracotta vertex-colour gradient that is repainted per render so it completes within the visible
wall, plus a four-light rig: a tight warm key, a large cool fill at about a sixth of the key, a rim
from behind, and a soft glow aimed at the wall. The world is warm and nearly off, exposure sits at
-0.45 and the view look is "AgX - Punchy". Note that `--only` runs save a partial .blend; run
`--no-render` afterwards to re-save the full scene.

Tricks worth stealing: a collar or scarf that hugs the body is a slab intersected with an offset of a
frozen snapshot of the surface; a unicorn horn is a cone displaced by a helical sine in its own local
frame; a rainbow along a tail is paint driven by arc-length along the tail's polyline; the fishbowl is
a spherical shell with a cylinder subtracted from the top and a glass material.

## Cards

`cards.py` turns each character into an index card like the originals and lays the set out like the
photo. Three stages, each re-runnable on its own:

```bash
blender -b --python cards.py -- --stage cats      # transparent renders; the studio sweep becomes a shadow catcher
blender -b --python cards.py -- --stage labels    # titles in Comic Sans MS Bold (closest marker on this Mac), transparent
blender -b --python cards.py -- --stage compose   # renders/cards/NN_Name.jpg and cat_breads_cards.jpg
```

Titles are transcribed as written on the cards, spelling included ("the invetigator one", "the show
of!" with its "AND NO FARTING" footnote). The cover card is painted blue like the original. Two
gotchas: a shadow catcher under a dome light records a faint alpha across the whole frame, so the
card renders switch the world off and the compositor clips alphas below 1.5 percent; and Blender's
`Image.save()` takes a `quality` argument for JPEG. Compositing is plain numpy on Blender's image
pixel buffers, so nothing outside Blender is needed.

## Rigging and animation

`rig.py` gives every character an armature and an idle animation, then saves `cat_breads_rigged.blend`
with the whole group posed in the hangout layout:

```bash
blender -b --python rig.py                                   # rig all 23, save cat_breads_rigged.blend
blender -b --python rig.py -- --preview --frames 96          # also render an EEVEE preview to renders/anim/
blender -b --python rig.py -- --quick --only LuckyCat --preview
```

Bones come from the anatomy each `Cat` records while it builds (body, head, ears, tail); the tail
becomes a three-bone chain sampled by arc length. Skin weights are not painted or heat-solved: each
vertex gets a softmin over its distances to the tagged SDF parts, so the head/body blend follows the
same smooth union that shaped the mesh, and tail weight is split between the chain bones by arc-length
position. Props stay static except wings and the koban, which ride on the body bone.

The idle motion is F-curve noise on every bone (breathing scale on the body, nod/turn/tilt on the
head, quick ear twitches, a wave travelling up the tail), with independent phases per cat, so the group
moves without a single keyframe. Open the .blend, scrub the timeline, and keyframe on top of it as you
would any rig. Facial animation (blinks, mouths) is not in the rig because those features are baked
geometry and paint; the SDF route to that is re-meshing per frame with time-varying parameters.

Blender 5.2 notes: actions are layered, so F-curves are reached through the action's channel bags, and
video output needs `image_settings.media_type = "VIDEO"` before `file_format = "FFMPEG"`.

## Web: the Three.js lounge

`export_web.py` exports every rigged character as its own Draco-compressed GLB (skinned mesh, named
bones, vertex colours, clearcoat) and writes the lounge layout; `web/` is a static Three.js page that
loads them and turns each cat's `head` bone toward the cursor.

```bash
blender -b cat_breads_rigged.blend --python export_web.py -- --target 24000   # web/models/*.glb + web/layout.json
python3 -m http.server 8765 --directory web                                   # then open http://localhost:8765
```

Sizes: meshes are decimated to about 24k vertices per part on export, which keeps the whole cast
at roughly 5 MB. Three.js and the Draco decoder come from the jsdelivr CDN via an import map, so the
folder deploys to any static host as-is.

The room is procedural and responsive. `fitCamera()` derives the back wall's width from the camera
frustum (backing the camera off on narrow screens until an 18-unit room fits, letting the room grow to
44 units on wide ones) and rebuilds the furniture whenever the width changes: shelf groups anchor to
the wall's edges, the plant, lamp and floor spots spread with the width, and the couch, rug and side
table stay centred. Shelves: a walnut bookshelf, an oak cubby grid, a sage arched niche, white lacquer
floating slabs and brass hexagons, plus the photo of the original cards framed above the couch. Every cat has a named spot (`SPOT_OF` in main.js), so seating is
easy to rearrange. Drag to orbit within limits; the cursor look still works while orbiting.

### Touch (iPad)

The page is built for fingers as much as for a mouse. One finger orbits, two fingers pinch to zoom
(OrbitControls' touch handling, panning disabled), a tap presses a cat or the lamp and a double-tap
on the floor drops a treat. Taps are told apart from drags by a movement threshold that is wider for
touch than for a mouse (12 px against 6), the double-tap radius is wider too (48 px against 30), and
the proxy spheres used for picking grow by about a third under a finger so small cats are easy to
hit. A press that turns into a pinch is never counted as a tap, and a cancelled touch (a system
gesture, a palm) is dropped. The cats look at your finger while it is on the glass; two and a half
seconds after it lifts their gaze drifts back to the viewer. Because iOS only unlocks audio on the
release of a gesture, the audio context is also started on pointer-up and touch-end. The page itself
is pinned: `touch-action: none`, no overscroll, no text selection or long-press callout, page
pinch-zoom blocked, the viewport set with `viewport-fit=cover` and the mute button padded by the
safe-area insets and enlarged for coarse pointers. Tablets render at a pixel ratio of at most 1.5
to keep the frame rate up, and the web-app meta tags let it be added to the home screen as a
full-screen app.

To use it on an iPad on the same Wi-Fi, start the server and open `http://<your-mac's-ip>:8765/`
in Safari (the Python server listens on every interface). Nothing on the page needs a secure
context, so plain HTTP over the LAN is fine.

Animation on the page is a pose assembly per frame: spot transform, cursor look, idle sway, then the
offsets of whatever move is playing. Clicking or tapping a cat (picked by proxy spheres, never by
raycasting skinned meshes) plays a random move from the palette in `MOVES`: hop, double hop, spin,
wiggle, stretch, shake, nod, surprise, sleepy, dance and bow, never the same one twice in a row.
Cats with dot eyes have `eye.L`/`eye.R` bones (vertical, sharply weighted to the eye spheres), so a
blink is a scale on the bone; blinks and ear flicks run on random schedules per cat. A debug hook,
`window.lounge.play(name, move)`, triggers a specific move from the console.

How the look works (web/main.js): the pointer is projected onto a plane in front of the group; for
each cat the direction to that point is expressed in the cat's own frame (glTF puts the cats facing
+Z), clamped to a comfortable yaw/pitch, turned into a world-space rotation and re-expressed in the
head bone's local frame on top of its rest pose, then slerped with a per-cat lag. The body follows a
fraction of the yaw; ears and tails run on sine idles. Glass is swapped for simple translucency.

## Shader effects

A small effects layer (`shader FX` in main.js) injects GLSL into the standard materials with
`onBeforeCompile`, so lighting, shadows and skinning keep working and no material is rewritten:

- **Felted fuzz.** Every opaque cat material perturbs its shading normal with value noise sampled
  in skinned object space (so the grain sticks to the skin as the cat moves), speckles the vertex
  colour a little and lightens the silhouette with a soft fresnel halo of fibres. Eyes and glass
  skip the fuzz so they stay glossy. `FX.fuzz` sets the strength.
- **Petting ripple.** Pressing or stroking a cat sends a dent that recovers and a ring that runs
  outward across its surface, displaced along the skinned normal in the vertex shader. A drag that
  starts on a cat pets it instead of orbiting the camera; the touch point is the ray's nearest
  point on the cat's proxy sphere, converted to the cat's local space, and strokes add a ripple
  every 90 ms along the way. A ripple lives about two seconds; the cat keeps looking at the finger.
- **Floor ripples.** The floor material carries a ring buffer of eight ripples (position, birth
  time, strength). In the fragment shader each live ripple bends the wood-grain UVs radially and
  tilts the normal, so the lights catch expanding rings. Treat landings, floor taps and every hop
  of a travelling cat ring the floor; the old ring meshes remain only for the dust of a fight.
- **Plant sway.** The leaves flex across their thin axis in the vertex shader, more toward the tip,
  phased by where each leaf stands, with a faster flutter on top.
- **Lamp cone.** A double-sided additive cone from the shade to the floor, brighter near the shade,
  thinner where it is seen edge-on, with a faint flicker, plus seventy drifting dust motes as a
  point cloud. Both fade with the lamp, so they vanish at night.
- **Impact pulse and shake.** When a treat first hits the floor, an EffectComposer pass draws an
  expanding chromatic shockwave from the treat's screen position (colour fringes split away from
  the impact, the image is pulled toward it and pushed by the ring) while the camera shakes and
  rolls for a moment. Later bounces tick at a quarter of the strength. The composer (with a
  multisampled half-float target so the pass does not alias) only renders while a pulse is alive;
  the rest of the time the scene renders directly, so the effect costs nothing at rest.

## Icon, home-screen app and hosting

`export_icon.py` renders the app icon with the same studio as the cards: the Mascot cat, face on
through a 70 mm lens, on the cream-to-terracotta sweep, framed with enough margin for the rounded
corners iOS applies and the circular safe zone of a maskable icon:

    blender -b --python export_icon.py            # web/icons/icon-1024.png (--only <Name> for another cat)
    ./make_icons.sh                                # touch icon, manifest sizes and favicons via sips

That gives `apple-touch-icon.png` (180 px, what iOS uses on the home screen), `icons/icon-192.png`
and `icons/icon-512.png` for the web app manifest, `favicon-32.png`, `favicon-64.png` and a
`favicon.ico` that wraps 16, 32 and 48 px PNGs. `manifest.webmanifest` names the app "Cat Breads",
asks for standalone display and the terracotta theme colour, and together with the
`apple-mobile-web-app-*` meta tags in the page makes "Add to Home Screen" on an iPad produce a
full-screen app with the cat icon.

The site is static, so hosting is the `web/` folder as a Vercel project (`cat-breads-lounge`,
live at https://cat-breads-lounge.vercel.app, linked from inside `web/` so the renders and .blend
files never upload; `.vercelignore` keeps the CLI's `.env.local` token file out too). `web/vercel.json` sets
cache headers: models and audio for a week with stale-while-revalidate, icons for a day, the page
and script always revalidated. To ship a change:

    cd web && npx vercel deploy --prod


Each cat has a voice in `web/audio/<Name>.mp3`, generated through the Comfy Cloud MCP with ElevenLabs
sound generation (one 1.5 s prompt per cat: a bell jingle for the Lucky Cat, a bubbly echo for the
Explorer, a bee buzz for the Bumble Cat, and so on), then trimmed, loudness-normalised and encoded
with ffmpeg. `web/audio/ambient.mp3` is the background loop. The FLAC originals are in
`renders/audio_src/`.

On the page, audio runs through Web Audio: voices are decoded once and played as buffer sources with
a little random playback-rate variation on every press; the ambient track loops gaplessly through a
buffer source and fades in on the first interaction, since browsers only allow sound after a gesture.
Treat impacts are synthesized too (`thud` in main.js): a triangle thump whose pitch falls, plus a
few milliseconds of bandpassed noise for the click, panned by where the biscuit lands. Every bounce
sounds, and the impact speed sets the gain, the starting pitch (harder hits land lower), the ring
time and the click's brightness, so the drop from the ceiling thumps and the last little bounces
tick. The page starts muted. The round music-note button in the corner brings the music and the meows in
and mutes them again; it shows a slashed note while muted.

On an iPhone, Safari runs Web Audio in an "ambient" audio session, which the ringer switch silences
even though media playback is not. The page asks for a "playback" session through the Audio Session
API (`navigator.audioSession.type = 'playback'`, Safari 16.4 and later) before the context is
created, and on older iOS it starts a looping silent WAV through an `<audio>` element instead, which
promotes the session the same way. WebKit also drops the context into an "interrupted" state after
a phone call, the lock screen or an app switch, so the unlock resumes whenever the state is not
"running" and again when the page becomes visible. The first gesture also starts a one-sample
silent buffer, the classic iOS unlock. Append `?ios=1` to the URL to exercise the iOS path on a
desktop browser.

Music note: Comfy Cloud lists a YuE2 text-to-music template, but its checkpoint is not deployed on
the Cloud workers yet (the job fails with the checkpoint name "not a valid value", and the model
catalog has no YuE entries), so the loop was generated with ACE-Step 1.5 instead. The YuE2 call to
retry later is `run_template("audio_yue2_text2music", input_overrides={...})` with the inputs
addressed by interior node ids (`33:36` style, `33:37` lyrics, `33:31` planning, `33:25` duration,
`33:34` seed), because the template's slot addresses do not resolve.

## The sign

`export_sign.py` extrudes and bevels a line of text in any installed font and exports it as
`web/models/sign.glb` (Draco). "For Lane" uses SignPainter HouseScript; a contact sheet of twelve
candidates showed script and clean display faces extrude well while rough handwriting fonts and
Party LET come out ragged. The text must be rotated to stand upright before export, or glTF's axis
conversion leaves it lying flat and the page shows only the extruded edges.

On the page the sign scales with the room width (capped so wide screens don't get a billboard) and
hangs above the framed photo. It is lit by two spotlights with brass fixtures on the sides, peach-gold
from the left and turquoise from the right, each aimed at its own half so the colours blend across
the middle and throw coloured shadows onto the wall. The camera's field of view was widened so the
top of the wall stays in frame on landscape screens.

```bash
blender -b --python export_sign.py -- "For Lane" "/System/Library/Fonts/Supplemental/SignPainter.ttc"
```

## Night mode

The camera sits low, near cat eye level, and can tilt a little upward. It can never dip below the
floor: `keepCameraAboveFloor` recomputes the orbit's maximum tilt every frame from the current zoom
so the eye stays at least 0.6 units above the boards. Clicking the floor lamp
cross-fades the whole rig between day and night (`applyMood` in main.js): the key, fill and rim dim
into cool moonlight, the hemisphere light turns to a dark blue sky, the lamp and its bulb go out, the
sign's spots drop to a third and its letters take on a soft glow, and the cats get a faint warm lift
so they stay readable. Five nightlights come up near the cats, each a small emissive prop with a warm
point light: a mushroom lamp on the bookshelf, a candle jar on the side table, a star on the top
floating shelf, a salt lamp by the plant, and a glow under the couch. Everything interpolates over
about a second, and a synthesized switch click plays through the audio graph.

Glowing eyes at night need no new geometry: at load, each cat's triangles whose vertices are skinned
to the `eye.L`/`eye.R` bones are moved into their own material group with an emissive clone of the
body material, and a small additive halo sprite is parented to each eye bone, so the glow follows head
turns and squashes with blinks. `EYE_COLOR` in main.js gives a few cats their own colour (red for the
Devil, violet for the Unimeow, blue for the Siamese); the rest use a green-gold tapetum shine. Cats
drawn with closed, happy or x eyes have no eye bones and stay dark, which reads as asleep.

## Treats

Double-press (or double-tap) an open patch of floor and a fish biscuit drops from above, tumbling, and
bounces to rest exactly on the spot with a ripple. The nearest free roaming cat (`TRIPPERS` in main.js:
Mascot, Box Tester, Stretcher, Lucky Cat, Unimeow, Large Hearted) turns to watch it fall, hops across at
about three units a second once it has settled (couch cats hop down first), stops with its nose on it,
meows, and eats it in three bites with chewing motions, ears bobbing and a synthesized crunch, then
hops back and settles into its place. Cats in boxes, bags, cups and bowls stay put. If everyone is
busy the treat waits on the floor and the next cat to come free goes for it; presses inside the couch
are pushed out in front of it. The trip is a small state machine (watch, go, wait, fight, sulk, eat,
back, settle) that overrides a cat's base transform while active, so the cursor look, idle, blinks
and night-time eye glow keep running on top.

### Rivalry

If the second-nearest free cat is nearly as close as the nearest (within 1.5x its distance, or 1.5
units of it, and under 9 units away), both go for the treat. `assignTreats` gives each a stopping
point on its own side of the biscuit: cats arriving from similar directions are fanned out to either
side of their mean approach, cats arriving from opposite sides simply face off across it. The first to
arrive crouches with flat ears and a raised tail and waits; when the second lands both switch to a
scuffle of about two and a half seconds: alternating lunges toward each other, hops, body rolls,
head shakes, ears pinned, lashing tails, dust-coloured ripples kicked up around the treat and
pitched-up meows from both. Each cat looks at its rival instead of the cursor for the duration. The
winner is drawn weighted by size (the bigger cat usually wins), turns back to the treat and eats it
as usual; the loser sulks for a second with its head down and ears back, then trudges home slowly
with small hops before settling. Everything is driven by the same trip state machine, so a cat
pressed mid-fight ignores the press and a third treat dropped meanwhile waits for a free cat.
