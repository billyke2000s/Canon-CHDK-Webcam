"""Synthetic USB bytes through real PTP, decoder, and native media encoder."""
import struct
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_ptp import FakeTransport, container, response, device_info
from canon_webcam.ptp import CHDK_OPERATION
from canon_webcam.runtime import USBSource


class PipelineIntegrationTests(unittest.TestCase):
    def test_wire_to_playable_recording(self):
        import av
        from canon_webcam.media import VideoRecorder, EncodingSettings
        # Real 2.2 header/descriptor, signed chroma neutral, 4x3 display pixels.
        pixels = bytes([0, 160, 0, 160, 160, 160]) * 12
        payload = (struct.pack('<8i', 2, 2, 0, 0, 0, 32, 0, 0) +
                   struct.pack('<9i', 0, 68, 8, 8, 6, 0, 0, 0, 0) + pixels)
        wire = (container(2, 0x1001, 0, device_info()) + response(0) +
                response(0) + response(1, 2, 9) +
                container(2, CHDK_OPERATION, 2, payload) + response(2, len(payload)) +
                response(3))
        transport = FakeTransport([wire[i:i+7] for i in range(0, len(wire), 7)], partial_write=3)
        source = USBSource()
        with patch('canon_webcam.usb.discover_cameras', return_value=['synthetic']), \
             patch('canon_webcam.usb.PyUSBTransport.open', return_value=transport):
            source.connect()
            frame, count = source.read()
            source.close()
        self.assertEqual(count, len(payload))
        self.assertEqual(frame.rgb.shape, (6, 8, 3))
        self.assertEqual(frame.rgb[0, 0].tolist(), [160, 160, 160])
        self.assertTrue(transport.closed)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'wire.mkv'
            with VideoRecorder(path, EncodingSettings(width=32, height=24)) as recorder:
                for n in range(6):
                    recorder.write(frame.rgb, frame.timestamp_ns + n * 42_000_000)
            with av.open(str(path)) as video:
                decoded = list(video.decode(video=0))
            self.assertEqual(len(decoded), 6)
            self.assertEqual((decoded[0].width, decoded[0].height), (32, 24))


if __name__ == '__main__':
    unittest.main()
