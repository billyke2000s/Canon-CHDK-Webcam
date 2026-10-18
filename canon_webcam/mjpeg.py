"""Basic MJPEG JPEG-frame extraction for byte streams.

Validates frame delimiters only, not full JPEG image syntax. Intended for
diagnostics; production capture should also validate decode and frame size.
"""


class MjpegDecoder:
    def __init__(self, max_frame_bytes=8 * 1024 * 1024):
        if max_frame_bytes < 4:
            raise ValueError("JPEG frame limit must be at least 4 bytes")
        self.buffer = bytearray()
        self.max_frame_bytes = max_frame_bytes

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(b"\xff\xd8")
            if start < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer.endswith(b"\xff") else b""
                break
            if start:
                del self.buffer[:start]
            end = self.buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(self.buffer) > self.max_frame_bytes:
                    self.buffer.clear()
                    raise ValueError("MJPEG frame exceeds configured limit")
                break
            end += 2
            if end > self.max_frame_bytes:
                self.buffer.clear()
                raise ValueError("MJPEG frame exceeds configured limit")
            frames.append(bytes(self.buffer[:end]))
            del self.buffer[:end]
        return frames
