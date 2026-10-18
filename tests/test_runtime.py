import time
import unittest
from canon_webcam.runtime import CaptureController, CaptureOptions, SimulatedSource


def wait_for(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('worker did not reach expected state')


class RuntimeTests(unittest.TestCase):
    def test_capture_preview_stop_and_restart(self):
        c = CaptureController(CaptureOptions())
        for _ in range(2):
            c.start()
            wait_for(lambda: c.snapshot()['frames'] >= 3)
            frame = c.poll_frame()
            self.assertIsNotNone(frame)
            self.assertEqual(frame.rgb.shape, (480, 640, 3))
            self.assertEqual(c.snapshot()['usb_mbps'], 0)
            c.stop()
            self.assertEqual(c.snapshot()['state'], 'stopped')
        self.assertFalse(any(t.is_alive() for t in c._threads))

    def test_reconnect(self):
        class DisconnectOnce(SimulatedSource):
            connected = 0
            def connect(self):
                self.connected += 1
            def read(self):
                if self.connected == 1:
                    raise TimeoutError('simulated cable removal')
                return super().read()
        c = CaptureController(CaptureOptions(), source_factory=DisconnectOnce)
        c.start()
        wait_for(lambda: c.snapshot()['frames'] >= 2)
        c.stop()
        self.assertEqual(c.snapshot()['reconnects'], 1)

    def test_failure_without_reconnect(self):
        class BadSource(SimulatedSource):
            def connect(self):
                raise TimeoutError('test timeout')
        c = CaptureController(CaptureOptions(reconnect=False), source_factory=BadSource)
        c.start()
        wait_for(lambda: c.snapshot()['state'] == 'error')
        c.stop()
        self.assertIn('test timeout', c.snapshot()['error'])

    def test_slow_output_drops_frames_and_closes(self):
        class SlowRecorder:
            closed = False
            def __init__(self, *args):
                pass
            def write(self, *args):
                time.sleep(.15)
            def close(self):
                SlowRecorder.closed = True
        c = CaptureController(CaptureOptions(fps=30, recording='unused.mkv', buffer_size=1),
                              recorder_factory=SlowRecorder)
        c.start()
        wait_for(lambda: c.snapshot()['dropped'] > 2)
        self.assertLessEqual(c._frames.qsize(), 1)
        self.assertLessEqual(c._preview.qsize(), 1)
        c.stop()
        self.assertTrue(SlowRecorder.closed)

    def test_invalid_config(self):
        for config in [CaptureOptions(fps=60), CaptureOptions(buffer_size=0),
                       CaptureOptions(bitrate=61), CaptureOptions(mode='native')]:
            with self.assertRaises(ValueError):
                CaptureController(config)
