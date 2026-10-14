# Paintify Live for Blender

Paintify Live paints **whatever the active 3D Viewport shows** as a live
overlay, and paints **final renders** (stills, image sequences and movies) the
same way. It uses the GPU Hertzmann stroke pipeline from
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
Click **Start Live Paint**. The **Look** inspector has the same independent
brush, stroke, colour, ground, finish, and motion settings as current Brushkit.
Choose one of 23 era brush textures or the classic tile brush. **Radius set**
changes only the stroke sizes; it no longer replaces the entire painting look.
Expandable sections contain material, direction, palette, surface, effects,
variation, quality, and motion controls. Blender keeps its native theme and widgets.

**Load Look** and **Save Look** use Brushkit's version 1 `.sbr` files, including
the complete material block, palette, and historical per-layer overrides.
**Use Global Stroke Settings** clears imported layer overrides so the global
length, detail, and curvature controls apply to every layer. Older `.blend`
files retain their five-preset settings through a one-time migration.

Unchanged sources reuse the completed painting. Moving inputs can use
Lucas-Kanade motion tracking, paint renewal, and fresh paint to limit smearing.
**Paint FPS** sets the stop-motion cadence and **Resolution** trades preview
detail for speed. The panel shows the measured paint rate. When nothing in
the scene, the view or the settings has changed for a moment, the overlay
stops repainting and the panel shows **Paused**; any change resumes it.

**Stroke stability** keeps last frame's strokes where the image barely
changed, so render noise does not make strokes flicker. Wherever the image
does change, for example around a moving object, the old paint is cleared and
repainted, so nothing is left behind.

In **camera view** the overlay paints exactly the camera frame, through the
camera's projection at the render's aspect. That is the preview of the
render. Outside camera view it paints the whole viewport.

## Render

In the **Render** inspector tab (also at the bottom of Blender's **Render** menu):

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
  paints, drives the overlay and renders a still, a PNG sequence and an MP4.
  It also runs under the `bpy` 5.2 module; on Linux wrap it in `xvfb-run`.
- Blender 5.1 on Mac does not expose drawing GPU functions in background mode.
  Use `blender --factory-startup --python tools/blender_desktop_test.py` there.
  This opens a temporary desktop instance, runs the tests on Metal, and quits.
- `python tools/sync_brushkit.py /path/to/Paintify-GPU` refreshes the shared brush
  definitions and portable shaders from the standalone repository. It requires
  a C++17 compiler only for development; packaged users need no compiler.

Version 0.4.0 was tested with Blender 5.1.1 on Apple M1/Metal. Shader checks also
compile every stage as Vulkan and OpenGL 4.3 GLSL. Windows/Linux runtime testing
and native sidebar visual inspection remain separate from those compiler checks.

The Live panels use their own identifiers and can coexist with the older
Paintify geometry-nodes extension. Its geometry and compositor tools remain
available separately from the GPU overlay.
