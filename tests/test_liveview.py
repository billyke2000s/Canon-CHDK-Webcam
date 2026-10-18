import random
import struct
import unittest
from canon_webcam.liveview import (parse_viewport, to_rgb, to_rgb_reference,
                                  ppm_bytes, normalize_rgb)


def response(kind=0, pixels=b'\x00\x80\x00\x80\x80\x80', width=4,
             stride=4, height=1, margins=(0, 0, 0, 0), minor=2, aspect=0):
    header_size = 32 if minor >= 2 else 28
    fields = [2, minor, aspect, 0, 0, header_size, 0]
    if minor >= 2:
        fields.append(0)
    return (struct.pack('<' + 'i' * len(fields), *fields) +
            struct.pack('<9i', kind, header_size + 36, stride, width, height,
                        *margins) + pixels)


class LiveViewTests(unittest.TestCase):
    def test_yuv8(self):
        v = parse_viewport(response())
        self.assertEqual(to_rgb(v), bytes([128] * 12))
        self.assertTrue(ppm_bytes(v).startswith(b'P6\n4 1\n255\n'))

    def test_full_luma_range(self):
        v = parse_viewport(response(pixels=bytes([0, 0, 0, 16, 235, 255])))
        self.assertEqual(to_rgb(v), bytes([0]*3 + [16]*3 + [235]*3 + [255]*3))

    def test_yuv8b_and_yuv8c_chroma_difference(self):
        b = parse_viewport(response(2, bytes([128, 80, 128, 80]), 2, 2))
        c = parse_viewport(response(3, bytes([0, 80, 0, 80]), 2, 2))
        self.assertEqual(to_rgb(b), bytes([80] * 6))
        self.assertEqual(to_rgb(b), to_rgb(c))
        signed = parse_viewport(response(3, bytes([255, 100, 255, 100]), 2, 2))
        self.assertEqual(to_rgb(signed)[:3], bytes([99, 101, 98]))

    def test_numpy_matches_reference(self):
        rng = random.Random(19)
        for kind, stride, rowbytes in ((0, 12, 18), (2, 12, 24), (3, 12, 24)):
            for width in (1, 3, 7, 12):
                v = parse_viewport(response(kind, rng.randbytes(rowbytes * 3), width, stride, 3))
                self.assertEqual(to_rgb(v), to_rgb_reference(v))

    def test_row_padding_and_odd_visible_width(self):
        v = parse_viewport(response(2, bytes([128, 10, 128, 20, 128, 99, 128, 99,
                                              128, 30, 128, 40, 128, 99, 128, 99]), 1, 4, 2))
        self.assertEqual(to_rgb(v), bytes([10]*3 + [30]*3))

    def test_margins_are_display_metadata_not_buffer_offsets(self):
        v = parse_viewport(response(pixels=bytes([0, 50, 0, 50, 50, 50]) * 3,
                                    height=3, margins=(0, 0, 0, 0)))
        self.assertEqual(v.display_aspect, 4/3)
        self.assertEqual(len(to_rgb(v)), 36)
        wide = parse_viewport(response(pixels=bytes([0, 50, 0, 50, 50, 50]) * 3,
                                       height=3, margins=(0, 1, 0, 1)))
        self.assertAlmostEqual(wide.display_aspect, 20/9)

    def test_normalize_and_rotation(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest('NumPy optional dependency unavailable')
        v = parse_viewport(response(pixels=bytes([0, 50, 0, 50, 50, 50]) * 3, height=3))
        self.assertEqual(normalize_rgb(v).shape, (3, 4, 3))
        self.assertEqual(normalize_rgb(v, 90).shape, (4, 3, 3))
        with self.assertRaises(ValueError):
            normalize_rgb(v, 45)

    def test_old_header(self):
        self.assertEqual(len(to_rgb(parse_viewport(response(minor=0)))), 12)

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

    def test_malformed_descriptors(self):
        for index, value in ((0, 1), (1, 0), (1, 32), (2, 3), (3, 5),
                             (4, -1), (5, -1), (6, 8193), (7, 8192)):
            data = bytearray(response())
            struct.pack_into('<i', data, 32 + index * 4, value)
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                parse_viewport(data)


if __name__ == '__main__':
    unittest.main()
