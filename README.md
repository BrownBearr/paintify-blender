# Paintify Live for Blender

Paintify Live paints **whatever the active 3D Viewport shows** as a live
overlay, and paints **final renders** (stills, image sequences and movies) the
same way. It uses the GPU Hertzmann stroke pipeline from
[paintify-GPU](https://github.com/BrownBearr/paintify-GPU): curved brush
strokes, relaxation, brush texture and impasto.

The painter runs on Blender's own `gpu` module, so Blender compiles it for
whatever backend it uses: Metal on macOS, Vulkan or OpenGL on Windows and
Linux. There is nothing to build and no external program.

## Install (Blender 4.2 or newer, macOS, Windows, Linux)

1. Run `python tools/package_addon.py` to make `paintify_gpu.zip`.
2. In Blender, choose **Edit > Preferences > Add-ons > Install from Disk**, pick
   `paintify_gpu.zip`, and enable **Paintify Live**.

If you installed an older Paintify Live that used `paintify-stream.exe`,
remove it first. The renderer path preference is gone.

## Viewport

Open a **3D Viewport**, press **N** for the sidebar, and open **Paintify**.
Click **Start Live Paint**. Adjust style, brush size, curvature, threshold,
brush texture, impasto, relaxation and opacity while looking at the viewport.
**Paint FPS** sets the stop-motion cadence and **Resolution** trades preview
detail for speed. The panel shows the measured paint rate.

In **camera view** the overlay paints exactly the camera frame, through the
camera's projection at the render's aspect. That is the preview of the
render. Outside camera view it paints the whole viewport.

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

- `python -m unittest discover -s tests -p "test_*.py"` runs the pure Python
  tests. The shader test compiles every stage as strict Vulkan GLSL when
  `glslangValidator` is installed (`brew install glslang`).
- `blender --background --factory-startup --python tests/blender_smoke.py`
  paints, drives the overlay and renders a still, a PNG sequence and an MP4.
  It also runs under the `bpy` 5.2 module; on Linux wrap it in `xvfb-run`.

`src/`, `shaders/` and `tools/build.bat` are the standalone Windows renderer
(`gpu-sbr`, OpenGL 4.6). The add-on does not use them. They are the reference
the add-on's shaders were ported from.
