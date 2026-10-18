"""Host media tests use synthetic RGB frames, never imply camera validation."""
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

from canon_webcam.media import EncodingSettings, VideoRecorder, VirtualCameraSink, fit_rgb

MEDIA_AVAILABLE = all(importlib.util.find_spec(m) is not None for m in ("av", "numpy"))


class SettingsTests(unittest.TestCase):
    def test_invalid_settings(self):
        for values in ({"width": 1919}, {"height": 0}, {"fps": 0}, {"fps": 61}, {"fps": 24.5}, {"width": True}, {"bitrate_mbps": 61}, {"codec": "raw"}, {"codec": "mjpeg", "encoder": "libx264"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                EncodingSettings(**values)

    def test_optional_dependency_error(self):
        with patch("canon_webcam.media.importlib.import_module", side_effect=ImportError("missing")):
            with self.assertRaisesRegex(RuntimeError, "Optional dependency"):
                VideoRecorder("uncreated.mkv")


@unittest.skipUnless(MEDIA_AVAILABLE, "install media extra for real encoding tests")
class MediaTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.rgb = np.full((48, 64, 3), (180, 80, 40), dtype=np.uint8)

    def test_letterboxing_preserves_aspect_and_source(self):
        import numpy as np
        out = fit_rgb(self.rgb, 128, 72)
        self.assertEqual(out.shape, (72, 128, 3))
        self.assertTrue(np.all(out[:, :16] == 0))
        self.assertTrue(np.all(out[:, 112:] == 0))
        self.assertTrue(np.all(out[:, 16:112] == self.rgb[0, 0]))
        np.testing.assert_array_equal(self.rgb[0, 0], [180, 80, 40])

    def test_bad_source(self):
        import numpy as np
        for source in (b"rgb", np.zeros((2, 2)), np.zeros((2, 2, 4), dtype=np.uint8)):
            with self.assertRaises(ValueError):
                fit_rgb(source, 64, 48)

    def test_real_roundtrip_h264_and_mjpeg(self):
        import av
        for codec in ("h264", "mjpeg"):
            with self.subTest(codec=codec), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "test.mkv"
                with VideoRecorder(path, EncodingSettings(width=64, height=48, codec=codec)) as sink:
                    self.assertEqual(sink.encoded_mbps, 0)
                    for i in range(12):
                        self.assertTrue(sink.write(self.rgb, 10_000_000_000 + (i * 1_000_000_000 + 23) // 24))
                    self.assertFalse(sink.write(self.rgb, 10_000_000_000))
                    self.assertEqual(sink.frames_written, 12)
                    self.assertEqual(sink.frames_dropped, 1)
                self.assertGreater(sink.encoded_bytes, 0)
                self.assertGreater(sink.encoded_mbps, 0)
                self.assertAlmostEqual(sink.encoded_mbps, sink.encoded_bytes * 8 / .5 / 1_000_000)
                with av.open(str(path)) as container:
                    frames = list(container.decode(video=0))
                self.assertEqual(len(frames), 12)
                self.assertEqual((frames[0].width, frames[0].height), (64, 48))
                times = [float(f.pts * f.time_base) for f in frames]
                self.assertEqual(times[0], 0)
                self.assertTrue(all(a < b for a, b in zip(times, times[1:])))
                decoded = frames[0].to_ndarray(format="rgb24")
                self.assertLess(abs(int(decoded[20, 20, 0]) - 180), 10)
                sink.close()
                with self.assertRaisesRegex(RuntimeError, "closed"):
                    sink.write(self.rgb)

    def test_timestamp_gaps_preserved_without_duplication(self):
        import av
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gaps.mp4"
            with VideoRecorder(path, EncodingSettings(width=64, height=48)) as sink:
                self.assertTrue(sink.write(self.rgb, 1_000_000_000))
                self.assertFalse(sink.write(self.rgb, 1_000_000_001))
                self.assertFalse(sink.write(self.rgb, 999_999_999))
                self.assertTrue(sink.write(self.rgb, 2_000_000_000))
            with av.open(str(path)) as container:
                times = [float(f.pts * f.time_base) for f in container.decode(video=0)]
            self.assertEqual(times, [0, 1])

    def test_hardware_unavailable_falls_back_before_output(self):
        import av
        real_create = av.CodecContext.create
        def create(name, mode):
            if name == "h264_nvenc":
                raise RuntimeError("No NVIDIA device")
            return real_create(name, mode)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("canon_webcam.media._dependency") as dependency:
                import numpy as np
                shim = types.SimpleNamespace(CodecContext=types.SimpleNamespace(create=create), open=av.open, VideoFrame=av.VideoFrame)
                dependency.side_effect = lambda name: shim if name == "av" else np
                with VideoRecorder(Path(tmp) / "fallback.mkv", EncodingSettings(width=64, height=48, encoder="h264_nvenc")) as sink:
                    self.assertEqual(sink.encoder_name, "libx264")
                    self.assertIn("No NVIDIA device", sink.fallback_reason)
                    sink.write(self.rgb, 1)

    def test_virtual_camera_mock_contract_and_cleanup(self):
        import numpy as np
        import av
        camera = Mock(device="OBS Virtual Camera")
        fake = types.SimpleNamespace(Camera=Mock(return_value=camera), PixelFormat=types.SimpleNamespace(RGB="RGB"))
        with patch("canon_webcam.media._dependency", side_effect=lambda name: {"av": av, "numpy": np, "pyvirtualcam": fake}[name]):
            with VirtualCameraSink(width=64, height=48) as sink:
                sink.write(self.rgb, 123)
                self.assertEqual(sink.device, "OBS Virtual Camera")
                self.assertEqual(sink.frames_written, 1)
            sink.close()
            camera.close.assert_called_once()
            camera.send.assert_called_once()
            fake.Camera.assert_called_once_with(width=64, height=48, fps=24, fmt="RGB", backend="obs")
            with self.assertRaises(RuntimeError):
                sink.write(self.rgb)

    def test_flushes_after_caller_failure(self):
        import av
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "error.mkv"
            with self.assertRaisesRegex(RuntimeError, "capture"):
                with VideoRecorder(path, EncodingSettings(width=64, height=48)) as sink:
                    sink.write(self.rgb, 1)
                    raise RuntimeError("capture failed")
            with av.open(str(path)) as container:
                self.assertEqual(len(list(container.decode(video=0))), 1)


if __name__ == "__main__":
    unittest.main()
