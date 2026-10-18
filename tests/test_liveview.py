import struct
import unittest
from canon_webcam.liveview import parse_viewport, to_rgb, ppm_bytes


def response(kind=0, pixels=b'\x80\x80\x80\x80\x80\x80', width=4, stride=4, height=1):
    return (struct.pack('<7i', 2, 2, 0, 0, 0, 28, 0) +
            struct.pack('<9i', kind, 64, stride, width, height, 0, 0, 0, 0) + pixels)


class LiveViewTests(unittest.TestCase):
    def test_yuv8(self):
        v = parse_viewport(response())
        self.assertEqual(len(to_rgb(v)), 12)
        self.assertTrue(ppm_bytes(v).startswith(b'P6\n4 1\n255\n'))

    def test_yuv8b(self):
        v = parse_viewport(response(2, b'\x80\x80\x80\x80', 2, 2))
        self.assertEqual(len(to_rgb(v)), 6)

    def test_truncated(self):
        with self.assertRaises(ValueError):
            parse_viewport(response()[:-1])

    def test_bad_major(self):
        data = bytearray(response()); data[:4] = struct.pack('<i', 3)
        with self.assertRaises(ValueError):
            parse_viewport(data)

    def test_bad_offset(self):
        data = bytearray(response()); data[20:24] = struct.pack('<i', 900)
        with self.assertRaises(ValueError):
            parse_viewport(data)


if __name__ == '__main__':
    unittest.main()
