"""Bounded, transport-agnostic packet framing for future USB streaming.

This is host-side infrastructure, not a CHDK protocol implementation.
Each frame is: magic(4), payload length(uint32 little endian), sequence(uint32),
timestamp microseconds(uint64), codec id(uint8), payload bytes.
"""
import struct
from dataclasses import dataclass

MAGIC = b"CWCM"
HEADER = struct.Struct("<4sIIQB")
CODECS = {"h264": 1, "mjpeg": 2}
CODEC_NAMES = {v: k for k, v in CODECS.items()}
MAX_FRAME_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class VideoPacket:
    sequence: int
    timestamp_us: int
    codec: str
    payload: bytes


def encode_packet(packet: VideoPacket) -> bytes:
    if packet.codec not in CODECS:
        raise ValueError("unknown codec")
    if not 0 <= packet.sequence <= 0xFFFFFFFF:
        raise ValueError("sequence out of range")
    if not 0 <= packet.timestamp_us <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("timestamp out of range")
    if not 0 < len(packet.payload) <= MAX_FRAME_BYTES:
        raise ValueError("invalid payload size")
    return HEADER.pack(MAGIC, len(packet.payload), packet.sequence,
                       packet.timestamp_us, CODECS[packet.codec]) + packet.payload


class PacketDecoder:
    """Incrementally decode framed packets, tolerating arbitrary read boundaries.

    Bad headers raise ValueError and clear buffered state rather than
    attempting unsafe unbounded resynchronization.
    """
    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[VideoPacket]:
        self._buffer.extend(data)
        output = []
        try:
            while len(self._buffer) >= HEADER.size:
                magic, size, sequence, timestamp, codec = HEADER.unpack_from(self._buffer)
                if magic != MAGIC or not 0 < size <= MAX_FRAME_BYTES or codec not in CODEC_NAMES:
                    raise ValueError("invalid stream header")
                total = HEADER.size + size
                if len(self._buffer) < total:
                    break
                payload = bytes(self._buffer[HEADER.size:total])
                del self._buffer[:total]
                output.append(VideoPacket(sequence, timestamp, CODEC_NAMES[codec], payload))
        except ValueError:
            self._buffer.clear()
            raise
        return output

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)
