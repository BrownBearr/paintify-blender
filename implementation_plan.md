# Paintify Blender implementation

- [NEW] `blender_addon/paintify_gpu/__init__.py`: compositor node with image/movie source, paint controls, GPU execution, and output image.
- [NEW] `blender_addon/paintify_gpu/engine.py`: validate settings, assemble safe argument vectors, run bundled renderer, and report failures.
- [MODIFY] `tools/build.bat`, `vcpkg.json`: independent Windows build using the user's vcpkg checkout.
- [NEW] `README.md`, `system_architecture.md`: setup, use, and honest compositor integration limits.
- [NEW] `tests/test_engine.py`: command generation and error-path checks without Blender.

Verify Python tests and a Release GPU build. If Blender is installed, verify registration and a compositor paint round trip in Blender background mode.
