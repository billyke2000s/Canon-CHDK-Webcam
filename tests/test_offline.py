import os
import tempfile
import unittest
from canon_webcam.diagnostics import StreamMetrics
from canon_webcam.simulator import synthetic_packets
from canon_webcam.stream import encode_packet
from canon_webcam.inspect import inspect_file


class OfflineTests(unittest.TestCase):
    def test_simulator(self):
        packets = list(synthetic_packets(count=3, fps=24, payload_size=10))
        self.assertEqual([p.sequence for p in packets], [0, 1, 2])
        self.assertEqual(packets[1].timestamp_us, 41667)

    def test_capture_inspection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "capture.cwcm")
            with open(path, "wb") as file:
                for packet in synthetic_packets(count=3, payload_size=4):
                    file.write(encode_packet(packet))
            info = inspect_file(path, chunk_size=7)
            self.assertEqual(info["frames"], 3)
            self.assertEqual(info["payload_bytes"], 12)

    def test_truncated_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "bad.cwcm")
            with open(path, "wb") as file:
                file.write(encode_packet(next(synthetic_packets(count=1)))[:-1])
            with self.assertRaises(ValueError):
                inspect_file(path)

    def test_sequence_gap(self):
        clock = lambda: 10.0
        metrics = StreamMetrics(clock=clock)
        packets = list(synthetic_packets(count=4))
        metrics.observe(packets[0])
        metrics.observe(packets[3])
        self.assertEqual(metrics.snapshot().dropped, 2)


if __name__ == "__main__":
    unittest.main()
