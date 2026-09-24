# Paintify GPU for Blender

An independent Blender add-on and GPU renderer. The renderer is a source copy of
[paintify-GPU](https://github.com/BrownBearr/paintify-GPU), with no build or runtime
dependency on that repository. It reproduces the Hertzmann curved brush strokes,
relaxation, brush texture and impasto lighting used there.

## Build and install (Windows)

1. From this repository, run `tools\build.bat`. It builds `build\gpu-sbr.exe`.
   This requires MSVC Build Tools, CMake, Ninja and vcpkg. The script uses
   `%USERPROFILE%\vcpkg` when available.
2. In Blender 4.2 or newer, go to **Edit > Preferences > Add-ons > Install from
   Disk** and choose the `paintify_gpu.zip` made by `tools\package_addon.py`.
   Enable **Paintify GPU**.
3. In the add-on preferences, set **GPU Renderer** to this repository's
   `build\gpu-sbr.exe`. The GPU backend reads shaders from this repository's
   build path, so rebuild after moving the repository.

## Use

1. Open Blender's **Compositing** workspace and enable **Use Nodes**.
2. Press **Shift+A**, choose **Paintify GPU**, and place the node.
3. Pick an input image or MP4 in the node's **Input image or video** field.
4. Choose a style; adjust threshold, curvature, brush texture, impasto, lighting
   and relaxation iterations. For video, temporal stability is available too.
5. Optionally pick an output path. By default the output is written beside the
   input as `*_paintified.png` or `*_paintified.mp4`.
6. Click **Paint / Refresh**. Connect the node's **Image** output to a **Composite**
   or **Viewer** node. For MP4, the output image datablock plays as a movie.
   Set Blender's scene frame rate to match the source if you need frame-perfect
   playback. The renderer uses ffmpeg and ffprobe on PATH for video and preserves
   the source audio in the exported MP4.

The button processes the entire selected image or video; long videos block
Blender's UI until the renderer completes. Repaint after changing a slider.

## Current compositor boundary

This is a real Blender compositor node with an image output, but its source is
chosen with a file picker on the node. Blender's Python add-on API does not let
Python implement an arbitrary per-pixel compositor operation for an incoming
image socket. Consequently it cannot yet accept a wire from Render Layers or
another compositor node and paint that result live. This limitation is explicit
in the node: it offers no misleading input socket. A native C++ Blender
compositor integration would be needed for that capability.

`paintify-GPU` and `paintify-touchdesigner` are separate projects and are not
modified by this repository.
