import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blender_addon" / "paintify_gpu"))
from stream_bridge import LiveBridge, Look


@unittest.skipUnless(os.environ.get("PAINTIFY_STREAM"), "set PAINTIFY_STREAM to test the GPU")
class StreamIntegrationTests(unittest.TestCase):
    def test_two_painted_frames(self):
        width, height = 320, 180
        source = bytes(channel for y in range(height) for x in range(width)
                       for channel in (x * 255 // width, y * 255 // height, 100, 255))
        bridge = LiveBridge(os.environ["PAINTIFY_STREAM"])
        try:
            for sequence in (1, 2):
                deadline = time.monotonic() + 15
                while not bridge.submit(width, height, sequence, source, Look(relax=1, impasto=0.2)):
                    self.assertIsNone(bridge.error)
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.01)
                result = None
                while result is None:
                    self.assertIsNone(bridge.error)
                    self.assertLess(time.monotonic(), deadline)
                    result = bridge.take_latest()
                    time.sleep(0.01)
                self.assertEqual(result[:3], (width, height, sequence))
                self.assertEqual(len(result[3]), len(source))
                self.assertNotEqual(result[3], source)
        finally:
            bridge.close()
