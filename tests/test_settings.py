"""Preferences are untrusted local input and must survive interrupted writes."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canon_webcam.settings import AppSettings, load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_missing_settings_default_to_explicit_simulation(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory) / "missing.json")
        self.assertEqual(settings.mode, "simulate")
        self.assertFalse(settings.virtual_camera)

    def test_roundtrip_all_preferences(self):
        settings = AppSettings(mode="usb", width=1280, height=720, fps=15,
                               codec="mjpeg", bitrate=18, reconnect=False,
                               debug_logging=True, encoder="libx264")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "settings.json"
            save_settings(settings, path)
            self.assertEqual(load_settings(path), settings)
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_reject_invalid_fields(self):
        invalid = ({"mode": "native"}, {"width": 1920}, {"fps": 60},
                   {"fps": True}, {"bitrate": 61}, {"buffer_size": 0},
                   {"codec": "unknown"}, {"encoder": "shell-command"},
                   {"reconnect": "false"}, {"width": 640.0})
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                replace(AppSettings(), **fields).validate()

    def test_reject_corrupt_or_unversioned_settings(self):
        payloads = (b"{", b"\xff", b"[]", b'{}',
                    b'{"version": 1, "settings": {"unknown": 1}}',
                    b'{"version": 1, "settings": {"bitrate": "30"}}', b"x" * 65537)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for payload in payloads:
                with self.subTest(payload=payload[:50]):
                    path.write_bytes(payload)
                    with self.assertRaises(ValueError):
                        load_settings(path)

    def test_atomic_replace_failure_preserves_old_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_settings(AppSettings(), path)
            previous = path.read_bytes()
            with patch("canon_webcam.settings.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    save_settings(replace(AppSettings(), bitrate=25), path)
            self.assertEqual(path.read_bytes(), previous)
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_invalid_preferences_never_replace_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_settings(AppSettings(), path)
            with self.assertRaises(ValueError):
                save_settings(replace(AppSettings(), fps=60), path)
            self.assertEqual(json.loads(path.read_text())["settings"]["fps"], 24)


class HeadlessSmokeReportTests(unittest.TestCase):
    def test_success_report_explicitly_marks_synthetic_evidence(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from canon_webcam.gui import self_test
        controller = Mock()
        controller.snapshot.return_value = {"state": "streaming"}
        controller.poll_frame.side_effect = [SimpleNamespace(rgb=SimpleNamespace(shape=(480, 640, 3)),
                                                             width=640, height=480, timestamp_ns=index + 1)
                                             for index in range(12)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with patch("canon_webcam.runtime.CaptureController", return_value=controller), \
                    patch("canon_webcam.gui._media_self_test", return_value={"codecs": "mocked"}):
                self.assertEqual(self_test(path), 0)
            report = json.loads(path.read_text())
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["hardware_verified"])
        self.assertEqual(report["simulated_frames"], 12)
        controller.stop.assert_called_once()

    def test_capture_error_still_writes_failure_report(self):
        from unittest.mock import Mock
        from canon_webcam.gui import self_test
        controller = Mock()
        controller.poll_frame.return_value = None
        controller.snapshot.return_value = {"error": "synthetic transport failed"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with patch("canon_webcam.runtime.CaptureController", return_value=controller):
                self.assertEqual(self_test(path), 1)
            report = json.loads(path.read_text())
        self.assertEqual(report["status"], "failed")
        self.assertIn("transport failed", report["error"])
        controller.stop.assert_called_once()
