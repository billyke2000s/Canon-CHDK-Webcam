from dataclasses import dataclass


@dataclass(frozen=True)
class StreamConfig:
    codec: str = "h264"
    bitrate_mbps: int = 30
    width: int = 1920
    height: int = 1080
    fps: int = 24
    clean_overlay: bool = True

    def validate(self):
        if self.codec not in ("h264", "mjpeg"):
            raise ValueError("codec must be h264 or mjpeg")
        if not 1 <= self.bitrate_mbps <= 150:
            raise ValueError("bitrate must be 1..150 Mbps")
        if (self.width, self.height) not in ((1920, 1080), (1280, 720), (640, 480)):
            raise ValueError("unsupported requested resolution")
        if self.fps not in (24, 30):
            raise ValueError("requested fps must be 24 or 30")
        return self

    @property
    def bytes_per_second(self):
        return self.bitrate_mbps * 1_000_000 / 8
