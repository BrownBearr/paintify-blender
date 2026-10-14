# Paintify Live (Blender add-on)

This repository holds one thing: the Paintify Live Blender add-on.

- `blender_addon/paintify_gpu/`: the add-on (Python + GLSL on Blender's `gpu` module).
- `dist/paintify_live_mac.zip`, `dist/paintify_live_windows.zip`: the installable
  zips. Same contents; two names so each platform has an obvious download.
- `tools/package_addon.py`: rebuilds both zips. Other `tools/` scripts are
  development helpers for this add-on (desktop test runner, installer, Brushkit
  sync from the paintify-GPU repository); none of them ship.
- `tests/`: unit, shader-compile, dist and Blender smoke tests.

Rules:

- This is the single source of truth for Paintify Live. Make every change here,
  on a branch off `main`; do not start a parallel copy of the add-on elsewhere.
- Do not add other projects, renderers, apps or add-ons to this repository.
  The standalone paintify-GPU renderer lives in its own repository.
- Do not reintroduce external executables or platform-specific binaries. The
  add-on must run from the same zip on macOS (Metal), Windows and Linux.
- Keep the Blender module name `paintify_gpu`, so installing a new zip
  replaces an older install in place.
- After changing anything under `blender_addon/`, run
  `python tools/package_addon.py`, bump `bl_info["version"]` for user-visible
  changes, and commit the rebuilt zips with the source.
- Reading settings (look_from_settings, anything a panel or the overlay calls)
  must never write to the scene: Blender forbids writes while drawing.
- Before committing, run `python -m unittest discover -s tests -p "test_*.py"`.
  `test_dist.py` fails when the zips are stale. With Blender available, also run
  `blender --background --factory-startup --python tests/blender_smoke.py`.
