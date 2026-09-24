"""Small, Blender-independent bridge to the Paintify GPU executable."""

from pathlib import Path
import subprocess

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
PRESETS = {"impressionist", "expressionist", "pointillist", "wash", "detail"}


def command(executable, source, destination, *, preset="impressionist",
            threshold=50.0, curvature=1.0, brush_texture=0.45,
            impasto=0.0, impasto_light=0.0, relax=0, temporal_diff=12.0):
    executable, source, destination = map(Path, (executable, source, destination))
    if not executable.is_file():
        raise ValueError(f"GPU renderer not found: {executable}")
    if not source.is_file():
        raise ValueError(f"Input not found: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output must be different files")
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    is_video = source.suffix.lower() in VIDEO_SUFFIXES
    if not is_video and source.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("Input must be a supported image or video file")
    wanted = ".mp4" if is_video else ".png"
    if destination.suffix.lower() != wanted:
        raise ValueError(f"Output must end in {wanted} for this input")
    args = [str(executable), "--video" if is_video else "--in", str(source),
            "--out", str(destination), "--headless", "--preset", preset,
            "--threshold", str(threshold), "--curvature", str(curvature),
            "--brush-texture", str(brush_texture), "--impasto", str(impasto),
            "--impasto-light", str(impasto_light), "--relax", str(relax)]
    if is_video:
        args += ["--temporal-diff", str(temporal_diff)]
    return args


def paint(executable, source, destination, **settings):
    args = command(executable, source, destination, **settings)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Unknown renderer failure").strip()
        raise RuntimeError(message[-2000:])
    if not output.is_file():
        raise RuntimeError("Renderer exited successfully but did not write an output file")
    return output
