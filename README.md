# Paintify Live for Blender

Paintify Live paints **whatever the active 3D Viewport shows** and displays the
result as a live overlay. It uses the same GPU Hertzmann stroke pipeline as
[paintify-GPU](https://github.com/BrownBearr/paintify-GPU), including curved
brush strokes, relaxation, brush texture and impasto. There is no MP4 or image
picker in the add-on. Move the camera, orbit the model, scrub Blender's timeline,
or play animation; the overlay samples the viewport again.

This is an independent repository. Neither `paintify-GPU` nor the TouchDesigner
repo is required at build or runtime.

## Install (Windows, Blender 4.2+)

1. Run `tools\build.bat` in this repository. This builds
   `build\paintify-stream.exe` (live backend) and `build\gpu-sbr.exe` (standalone
   renderer). Requires MSVC Build Tools, CMake, Ninja and vcpkg.
2. Run `python tools\package_addon.py` to make `paintify_gpu.zip`.
3. In Blender, choose **Edit > Preferences > Add-ons > Install from Disk**, pick
   `paintify_gpu.zip`, and enable **Paintify Live**.
4. The add-on defaults to `%USERPROFILE%\paintify-blender\build\paintify-stream.exe`.
   If your checkout is elsewhere, set **Live GPU renderer** in add-on preferences
   to its `build\paintify-stream.exe`. Rebuild if you move the repository: the
   shader path is compiled into the renderer.

## Use

Open a **3D Viewport**, press **N** for the sidebar, and open **Paintify**. Click
**Start Live Paint**. Adjust style, curvature, threshold, brush texture, impasto,
relaxation and opacity while looking at the viewport. **Paint FPS** controls
the stop-motion cadence; **Resolution** trades detail for speed. The default is
12 painted frames per second at 50% viewport resolution. Click **Stop Live
Paint** to remove the overlay.
The panel shows measured paint FPS while the effect runs.

The overlay is a preview over one active viewport. It is not a compositor node,
does not alter Blender's final render, and does not write a video file. The
viewport is rendered into a smaller offscreen texture, read into memory, sent
to a persistent GPU renderer process and uploaded back as an overlay. Blender's
Python GPU buffer conversion and the two transfers may limit actual FPS,
especially at 1080p or with relaxation; 12 FPS is a target setting rather than
a benchmark guarantee. The renderer uses OpenGL 4.6 and the `gpu-sbr` shaders.

The Blender 5.2 viewport callback, GPU texture upload, and live renderer
round trip are tested in an isolated background Blender session. Interactive
paint rate depends on the viewport and GPU workload.

Developers can repeat that check with
`blender --background --factory-startup --python tests/blender_smoke.py` after
building the renderer.
