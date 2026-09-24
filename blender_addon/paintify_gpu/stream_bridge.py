"""Binary viewport-frame transport. Testable without Blender."""

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread
import struct
import subprocess

MAGIC = 0x31565050
REQUEST = struct.Struct("<4I6f2I")
RESPONSE = struct.Struct("<4I")
PRESETS = ("impressionist", "expressionist", "pointillist", "wash", "detail")
MAX_PIXELS = 3840 * 2160


@dataclass(frozen=True)
class Look:
    threshold: float = 50.0
    curvature: float = 1.0
    brush_texture: float = 0.45
    impasto: float = 0.0
    impasto_light: float = 0.0
    temporal_diff: float = 12.0
    relax: int = 0
    preset: int = 0


def encode_frame(width, height, sequence, rgba, look):
    if width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise ValueError("Viewport size is unsupported")
    if len(rgba) != width * height * 4:
        raise ValueError("Expected RGBA8 pixels")
    if not 0 <= look.preset < len(PRESETS) or not 0 <= look.relax <= 12:
        raise ValueError("Look settings are unsupported")
    return REQUEST.pack(
        MAGIC, width, height, sequence,
        look.threshold, look.curvature, look.brush_texture,
        look.impasto, look.impasto_light, look.temporal_diff,
        look.relax, look.preset,
    ) + rgba


def read_exact(pipe, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = pipe.read(remaining)
        if not chunk:
            raise EOFError("GPU renderer stopped responding")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def write_exact(pipe, data):
    view = memoryview(data)
    while view:
        count = pipe.write(view)
        if not count:
            raise BrokenPipeError("GPU renderer input pipe closed")
        view = view[count:]


def decode_frame(pipe):
    magic, width, height, sequence = RESPONSE.unpack(read_exact(pipe, RESPONSE.size))
    if magic != MAGIC or width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise ValueError("Invalid GPU renderer response")
    return width, height, sequence, read_exact(pipe, width * height * 4)


def flip_rows(rgba, width, height):
    """Switch between Blender's bottom-up and the renderer's top-down rows."""
    stride = width * 4
    return b"".join(rgba[y * stride:(y + 1) * stride] for y in range(height - 1, -1, -1))


class LiveBridge:
    """One in-flight frame; drop stale captures rather than building latency."""

    def __init__(self, executable):
        exe = Path(executable)
        if not exe.is_file():
            raise FileNotFoundError(f"Paintify stream renderer not found: {exe}")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0, creationflags=flags,
        )
        self.incoming = Queue(maxsize=1)
        self.outgoing = Queue(maxsize=1)
        self.error = None
        self.running = True
        self.inflight = False
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()

    def submit(self, width, height, sequence, rgba, look):
        if not self.running or self.error or self.inflight:
            return False
        try:
            self.incoming.put_nowait((width, height, sequence, rgba, look))
            self.inflight = True
            return True
        except Full:
            return False

    def take_latest(self):
        try:
            return self.outgoing.get_nowait()
        except Empty:
            return None

    def _run(self):
        try:
            while self.running:
                try:
                    frame = self.incoming.get(timeout=0.1)
                except Empty:
                    continue
                width, height, sequence, rgba, look = frame
                write_exact(self.process.stdin, encode_frame(width, height, sequence, rgba, look))
                result = decode_frame(self.process.stdout)
                if result[:3] != (width, height, sequence):
                    raise ValueError("GPU renderer returned the wrong frame")
                self.inflight = False
                try:
                    self.outgoing.put_nowait(result)
                except Full:
                    self.outgoing.get_nowait()
                    self.outgoing.put_nowait(result)
        except (BrokenPipeError, EOFError, OSError, ValueError) as exc:
            if self.running:
                self.error = str(exc)
        finally:
            self.running = False

    def close(self):
        self.running = False
        if self.process.poll() is None:
            self.process.terminate()
        self.thread.join(timeout=2)
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe:
                pipe.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
