"""Create the Blender installable add-on zip from this repo."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
addon = root / "blender_addon" / "paintify_gpu"
with ZipFile(root / "paintify_gpu.zip", "w", ZIP_DEFLATED) as archive:
    for path in sorted(addon.glob("*.py")):
        archive.write(path, f"paintify_gpu/{path.name}")
print(root / "paintify_gpu.zip")
