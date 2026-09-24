"""Create the Blender installable add-on zip from this repo."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
addon = root / "blender_addon" / "paintify_gpu"
files = sorted(addon.glob("*.py")) + sorted((addon / "shaders").glob("*.glsl"))
with ZipFile(root / "paintify_gpu.zip", "w", ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, f"paintify_gpu/{path.relative_to(addon).as_posix()}")
print(root / "paintify_gpu.zip")
