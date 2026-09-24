import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blender_addon" / "paintify_gpu"))
import engine


class EngineTests(unittest.TestCase):
    def test_image_and_video_commands(self):
        with patch.object(Path, "is_file", return_value=True):
            root = Path("C:/paintify-test")
            exe = root / "gpu-sbr.exe"
            image = root / "input.png"
            video = root / "input.mp4"
            image_args = engine.command(exe, image, root / "painted.png", relax=4, impasto=0.3)
            self.assertIn("--in", image_args)
            self.assertIn("--relax", image_args)
            self.assertIn("--impasto", image_args)
            self.assertNotIn("--temporal-diff", image_args)
            video_args = engine.command(exe, video, root / "painted.mp4")
            self.assertIn("--video", video_args)
            self.assertIn("--temporal-diff", video_args)

    def test_rejects_mismatched_output(self):
        with patch.object(Path, "is_file", return_value=True):
            root = Path("C:/paintify-test")
            exe = root / "gpu-sbr.exe"
            video = root / "input.mp4"
            with self.assertRaisesRegex(ValueError, "end in .mp4"):
                engine.command(exe, video, root / "painted.png")
            with self.assertRaisesRegex(ValueError, "different files"):
                engine.command(exe, video, video)


if __name__ == "__main__":
    unittest.main()
