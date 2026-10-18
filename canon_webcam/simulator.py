"""Deterministic synthetic packet stream for parser and metrics development.

Payloads are deliberately NOT valid H.264 or JPEG bitstreams.
"""
import argparse
from .stream import VideoPacket, encode_packet


def synthetic_packets(count=48, fps=24, codec="h264", payload_size=2048):
    if count < 0 or fps <= 0 or payload_size < 1:
        raise ValueError("invalid simulation parameters")
    for sequence in range(count):
        yield VideoPacket(sequence, round(sequence * 1_000_000 / fps),
                          codec, bytes([sequence % 256]) * payload_size)


def main():
    p = argparse.ArgumentParser(description="Generate framed synthetic packets (not playable video)")
    p.add_argument("--frames", type=int, default=48)
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--codec", choices=("h264", "mjpeg"), default="h264")
    p.add_argument("--output", default="synthetic.cwcm")
    args = p.parse_args()
    with open(args.output, "wb") as file:
        for packet in synthetic_packets(args.frames, args.fps, args.codec):
            file.write(encode_packet(packet))
    print(f"Wrote {args.frames} synthetic frames to {args.output} (not playable video)")


if __name__ == "__main__":
    main()
