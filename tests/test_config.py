import unittest
from canon_webcam.config import StreamConfig


class StreamConfigTests(unittest.TestCase):
    def test_default(self):
        self.assertEqual(StreamConfig().validate().bitrate_mbps, 30)

    def test_bandwidth(self):
        self.assertEqual(StreamConfig().bytes_per_second, 3_750_000)

    def test_reject_60_fps(self):
        with self.assertRaises(ValueError):
            StreamConfig(fps=60).validate()

    def test_reject_invalid_codec(self):
        with self.assertRaises(ValueError):
            StreamConfig(codec="raw").validate()


if __name__ == "__main__":
    unittest.main()
