# Paintify Live for Blender

Paintify Live paints **whatever the active 3D Viewport shows** as a live
overlay, and paints **final renders** (stills, image sequences and movies) the
same way. With **Paintify Scene** the brushwork belongs to the 3D objects
instead of the screen: a stroke painted on an object stays on its surface as
the object turns or the camera moves. It uses the GPU Hertzmann stroke
pipeline from
[paintify-GPU](https://github.com/BrownBearr/paintify-GPU): curved brush
strokes, relaxation, brush texture and impasto.

The painter runs on Blender's own `gpu` module, so Blender compiles it for
whatever backend it uses: Metal on macOS, Vulkan or OpenGL on Windows and
Linux. There is nothing to build and no external program.

## Install (Blender 4.2 or newer)

Download the zip for your platform from `dist/` (open the file on GitHub, then
**Download raw file**):

- macOS: [`dist/paintify_live_mac.zip`](dist/paintify_live_mac.zip)
- Windows: [`dist/paintify_live_windows.zip`](dist/paintify_live_windows.zip)

Both zips contain the same files; either works on Linux too. Don't unzip it.
In Blender, choose **Edit > Preferences > Add-ons > Install from Disk**, pick
the zip, and enable **Paintify Live**. Preferences should show version 0.4.0.

Installing replaces an older Paintify Live in place. If Blender still reports
`paintify-stream.exe`, an old 0.2.x copy is loaded: uninstall every Paintify
entry in Add-ons, remove any Script Directory that points at a checkout of this
repository, restart Blender and install again.

## Viewport

Open a **3D Viewport**, press **N** for the sidebar, and open **Paintify**.
Click **Start Live Paint**. Adjust style, brush size, curvature, threshold,
brush texture, impasto, relaxation and opacity while looking at the viewport.
**Paint FPS** sets the stop-motion cadence and **Resolution** trades preview
detail for speed. The panel shows the measured paint rate.

In **camera view** the overlay paints exactly the camera frame, through the
camera's projection at the render's aspect. That is the preview of the
render. Outside camera view it paints the whole viewport.

## Paintify Scene: strokes that stay on objects

**Paint space** in the panel chooses where strokes live:

- **Screen** (default) paints the image every frame, as before. Temporal
  stability keeps still regions, but strokes on a moving object are redrawn
  and swim across it.
- **Object** attaches each stroke on an object to that object's surface.
  From then on it is redrawn where that surface is: it turns with the object,
  moves with the camera, hides behind whatever passes in front and comes back
  when that has moved on. Surface that turns into view for the first time is
  painted then, and kept. The background (world) is painted in screen space.
- **World** attaches strokes to world positions instead: they stay put as the
  camera moves, and a moving object slides under them.

**Relight strokes** (on by default) recolours attached strokes from the
current frame, so shading and highlights follow the light while the strokes
stay put. Off keeps the colour each stroke was painted with, like paint on a
model. **Repaint Scene Strokes** forgets the attached strokes and lays them
down again from the current view; changing the style or any stroke setting
does the same. The panel shows how many strokes are attached.

Renders work the same way: each render job attaches strokes from its first
frame and carries them through the frame range. Anchors are points in an
object's own space, so rigid motion (object, parent and camera animation) is
followed exactly; a deforming mesh (armature, shape keys, simulation) is not
followed yet. Instanced geometry (particles, collection and Geometry Nodes
instances) hides strokes behind it but is painted in screen space.

## Render

In the **Render** subpanel (also at the bottom of Blender's **Render** menu):

- **Render Painted Image** renders the current frame with the scene's engine,
  paints it and opens it as the **Paintify Render** image. Save it from the
  Image Editor.
- **Render Painted Animation** renders the frame range and writes the scene's
  output: an image sequence at the output path, or a movie through Blender's
  own encoder when the output is a video format. Esc cancels.

Renders paint at full render resolution. Brush sizes scale with the frame, so
a 50% viewport preview and a 4K render get the same strokes relative to the
frame. The source is the render as the scene's colour management displays it,
the same image the overlay samples in the viewport. With **Stop-motion
render** on (default), each painted frame is held for scene FPS / Paint FPS
frames, as the viewport shows during playback. Turn it off to paint every
frame. Temporal stroke stability carries over from frame to frame as in the
viewport.

For the closest match between overlay and render, preview in camera view with
**Rendered** shading. Solid and Material Preview shading paint what those
modes show, which differs from the final engine. Movies do not carry the
scene's audio.

## Develop

This repository contains only the add-on (`blender_addon/paintify_gpu/`), its
tests and the packaging tool. See `CLAUDE.md` for the rules.

- `python tools/package_addon.py` rebuilds both zips in `dist/`. Commit them
  with any add-on change; `tests/test_dist.py` fails when they are stale.
- `python -m unittest discover -s tests -p "test_*.py"` runs the tests that
  don't need Blender. The shader test compiles every stage as strict Vulkan
  GLSL when `glslangValidator` is installed (`brew install glslang`).
- `blender --background --factory-startup --python tests/blender_smoke.py`
  paints, drives the overlay in Screen, Object and World space and renders a
  still, PNG sequences and an MP4. It also runs under the `bpy` 5.2 module; on
  Linux wrap it in `xvfb-run`.
