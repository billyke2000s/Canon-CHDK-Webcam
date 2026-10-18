"""Inspect offline CWCM capture files, without loading the entire file."""
import argparse
from .stream import PacketDecoder


def inspect_file(path, chunk_size=65536):
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    decoder = PacketDecoder()
    count = 0
    total = 0
    codecs = set()
    first_timestamp = None
    last_timestamp = None
    with open(path, "rb") as file:
        while chunk := file.read(chunk_size):
            for packet in decoder.feed(chunk):
                count += 1
                total += len(packet.payload)
                codecs.add(packet.codec)
                if first_timestamp is None:
                    first_timestamp = packet.timestamp_us
                last_timestamp = packet.timestamp_us
    if decoder.buffered_bytes:
        raise ValueError("truncated final packet")
    return {"frames": count, "payload_bytes": total,
            "codecs": sorted(codecs),
            "duration_seconds": ((last_timestamp - first_timestamp) / 1_000_000
                                 if count > 1 else 0.0)}


def main():
    p = argparse.ArgumentParser(description="Inspect an offline CWCM frame capture")
    p.add_argument("path")
    args = p.parse_args()
    for key, value in inspect_file(args.path).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
