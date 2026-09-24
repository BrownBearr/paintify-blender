import io
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blender_addon" / "paintify_gpu"))
import stream_bridge as bridge


class StreamTests(unittest.TestCase):
    def test_frame_round_trip_format(self):
        pixels = bytes(range(24))
        request = bridge.encode_frame(3, 2, 7, pixels, bridge.Look(relax=3, impasto=0.2))
        self.assertEqual(len(request), 48 + len(pixels))
        self.assertEqual(struct.unpack_from("<4I", request), (bridge.MAGIC, 3, 2, 7))
        response = io.BytesIO(bridge.RESPONSE.pack(bridge.MAGIC, 3, 2, 7) + pixels)
        self.assertEqual(bridge.decode_frame(response), (3, 2, 7, pixels))

    def test_rows_and_validation(self):
        pixels = bytes(range(24))
        self.assertEqual(bridge.flip_rows(pixels, 3, 2), bytes(range(12, 24)) + bytes(range(12)))
        self.assertEqual(bridge.flip_rows(bridge.flip_rows(pixels, 3, 2), 3, 2), pixels)
        with self.assertRaisesRegex(ValueError, "RGBA8"):
            bridge.encode_frame(3, 2, 0, b"short", bridge.Look())
        with self.assertRaises(EOFError):
            bridge.decode_frame(io.BytesIO(b""))


if __name__ == "__main__":
    unittest.main()
