import unittest
from canon_webcam.stream import VideoPacket, encode_packet, PacketDecoder, HEADER
from canon_webcam.mjpeg import MjpegDecoder


class PacketTests(unittest.TestCase):
    def test_fragmented_packet(self):
        p = VideoPacket(42, 1234567, "h264", b"\\x00\\x00\\x01\\x65")
        raw = encode_packet(p)
        d = PacketDecoder()
        self.assertEqual(d.feed(raw[:3]), [])
        self.assertEqual(d.feed(raw[3:HEADER.size + 1]), [])
        self.assertEqual(d.feed(raw[HEADER.size + 1:]), [p])

    def test_multiple_packets(self):
        p = VideoPacket(1, 100, "mjpeg", b"jpeg")
        self.assertEqual(PacketDecoder().feed(encode_packet(p) * 2), [p, p])

    def test_reject_bad_magic(self):
        d = PacketDecoder()
        with self.assertRaises(ValueError):
            d.feed(b"FAIL" + encode_packet(VideoPacket(1, 1, "h264", b"x"))[4:])
        self.assertEqual(d.buffered_bytes, 0)

    def test_reject_oversized_frame(self):
        raw = bytearray(encode_packet(VideoPacket(1, 1, "h264", b"x")))
        raw[4:8] = (0xFFFFFFFF).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            PacketDecoder().feed(raw)

    def test_reject_empty_payload(self):
        with self.assertRaises(ValueError):
            encode_packet(VideoPacket(1, 1, "h264", b""))


class MjpegTests(unittest.TestCase):
    def test_fragmented_frames_and_garbage(self):
        jpeg = b"\xff\xd8data\xff\xd9"
        d = MjpegDecoder()
        self.assertEqual(d.feed(b"garbage" + jpeg[:4]), [])
        self.assertEqual(d.feed(jpeg[4:] + jpeg), [jpeg, jpeg])

    def test_limit(self):
        d = MjpegDecoder(max_frame_bytes=5)
        with self.assertRaises(ValueError):
            d.feed(b"\xff\xd8longer")


if __name__ == "__main__":
    unittest.main()
