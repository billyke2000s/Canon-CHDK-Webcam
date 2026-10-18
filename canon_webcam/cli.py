import argparse
from .config import StreamConfig


def main():
    p = argparse.ArgumentParser(description="Canon CHDK webcam experimental configuration checker")
    p.add_argument("--codec", choices=("h264", "mjpeg"), default="h264")
    p.add_argument("--bitrate", type=int, default=30)
    p.add_argument("--resolution", choices=("1920x1080", "1280x720", "640x480"), default="1920x1080")
    p.add_argument("--fps", type=int, choices=(24, 30), default=24)
    args = p.parse_args()
    width, height = map(int, args.resolution.split("x"))
    config = StreamConfig(args.codec, args.bitrate, width, height, args.fps).validate()
    print(f"Requested: {config.width}x{config.height}@{config.fps} {config.codec} {config.bitrate_mbps} Mbps")
    print(f"Video payload: {config.bytes_per_second / 1_000_000:.2f} MB/s (excludes USB overhead)")
    print("NOTE: Configuration only. No USB connection or video streaming is implemented yet.")


if __name__ == "__main__":
    main()
