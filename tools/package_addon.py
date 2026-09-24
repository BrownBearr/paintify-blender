"""Builds the installable add-on zips in dist/.

The macOS and Windows zips hold the same files: the add-on is Python and GLSL
that Blender compiles for Metal, Vulkan or OpenGL on the machine it runs on.
Two names exist only so each platform has an obvious download. The zips are
deterministic (fixed timestamps, LF line endings), so rebuilding unchanged
source leaves them byte-identical.
"""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "blender_addon" / "paintify_gpu"
DIST = ROOT / "dist"
ZIPS = ("paintify_live_mac.zip", "paintify_live_windows.zip")


def addon_files():
    """{path inside the zip: file bytes} for everything the add-on ships."""
    files = sorted(ADDON.glob("*.py")) + sorted((ADDON / "shaders").glob("*.glsl"))
    return {f"paintify_gpu/{path.relative_to(ADDON).as_posix()}":
            path.read_bytes().replace(b"\r\n", b"\n") for path in files}


def build(path):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in addon_files().items():
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)


def main():
    DIST.mkdir(exist_ok=True)
    for name in ZIPS:
        build(DIST / name)
        print(DIST / name)


if __name__ == "__main__":
    main()
