"""Optional synchronous host media sinks; no camera-side encoding is implied.

The capture worker owns scheduling and bounded queues. These sinks do not create
threads or retain frames. Install the ``media`` extra for recording and the
``webcam`` extra plus OBS Studio's virtual camera for Windows webcam output.
"""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import importlib
import time


def _dependency(name):
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise RuntimeError(f"Optional dependency {name!r} is required for this output") from exc


@dataclass(frozen=True)
class EncodingSettings:
    width: int = 1280
    height: int = 720
    fps: int = 24
    codec: str = "h264"
    bitrate_mbps: int = 30
    encoder: str = "auto"
    low_latency: bool = True

    def __post_init__(self):
        for name in ("width", "height", "fps", "bitrate_mbps"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if not (16 <= self.width <= 4096 and 16 <= self.height <= 4096):
            raise ValueError("output dimensions must be between 16 and 4096")
        if self.width % 2 or self.height % 2:
            raise ValueError("output dimensions must be even")
        if not 1 <= self.fps <= 60:
            raise ValueError("host frame rate must be 1..60")
        if self.codec not in ("h264", "mjpeg"):
            raise ValueError("codec must be h264 or mjpeg")
        if not 2 <= self.bitrate_mbps <= 60:
            raise ValueError("host bitrate target must be 2..60 Mbps")
        allowed = ("auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf") if self.codec == "h264" else ("auto", "mjpeg")
        if self.encoder not in allowed:
            raise ValueError("encoder is incompatible with the selected codec")


def fit_rgb(rgb, width, height):
    """Scale with FFmpeg and pad with black, preserving source aspect ratio.

    Upscaling the CHDK viewport does not recover native recorded-video detail.
    """
    np = _dependency("numpy")
    av = _dependency("av")
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("expected a uint8 RGB array shaped (height, width, 3)")
    sh, sw = rgb.shape[:2]
    if not sh or not sw or max(sh, sw) > 8192:
        raise ValueError("invalid source dimensions")
    if (sw, sh) == (width, height):
        return np.ascontiguousarray(rgb)
    scale = min(width / sw, height / sh)
    tw, th = max(1, round(sw * scale)), max(1, round(sh * scale))
    resized = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24").reformat(width=tw, height=th, format="rgb24").to_ndarray()
    result = np.zeros((height, width, 3), dtype=np.uint8)
    x, y = (width - tw) // 2, (height - th) // 2
    result[y:y + th, x:x + tw] = resized
    return result


def _configure(context, settings, name):
    context.width, context.height = settings.width, settings.height
    context.time_base = Fraction(1, settings.fps)
    context.framerate = Fraction(settings.fps, 1)
    context.bit_rate = settings.bitrate_mbps * 1_000_000
    context.pix_fmt = "yuvj420p" if settings.codec == "mjpeg" else "yuv420p"
    context.gop_size = settings.fps
    context.max_b_frames = 0
    if name == "libx264":
        context.options = {"preset": "veryfast", **({"tune": "zerolatency"} if settings.low_latency else {})}
    elif name == "h264_nvenc" and settings.low_latency:
        context.options = {"tune": "ull", "zerolatency": "1"}


class VideoRecorder:
    """Write standard MKV/MP4/AVI files using source monotonic timestamps.

    Rate limiting drops excess frames, never duplicates missing frames. Bitrate
    is an encoder target, not a guaranteed wire rate or camera capability.
    Hardware availability is verified by opening its codec, then falls back to
    libx264. An encoder failure during recording is reported, not hidden.
    """
    def __init__(self, path, settings=None):
        self.settings = settings or EncodingSettings()
        self.frames_written = self.frames_dropped = 0
        self.encoded_bytes = 0
        self._origin_ns = None
        self._last_pts = -1
        self._closed = False
        self._container = None
        self.fallback_reason = None
        av = _dependency("av")
        s = self.settings
        candidates = ["mjpeg"] if s.codec == "mjpeg" else (["libx264"] if s.encoder == "auto" else list(dict.fromkeys([s.encoder, "libx264"])))
        failures = []
        for name in candidates:
            try:
                probe = av.CodecContext.create(name, "w")
                _configure(probe, s, name)
                probe.open()
                del probe
                self.encoder_name = name
                break
            except Exception as exc:
                failures.append(f"{name}: {exc}")
        else:
            raise RuntimeError("No usable host encoder: " + "; ".join(failures))
        if failures:
            self.fallback_reason = "; ".join(failures)
        try:
            self._container = av.open(str(Path(path)), mode="w")
            self._stream = self._container.add_stream(self.encoder_name, rate=s.fps)
            _configure(self._stream.codec_context, s, self.encoder_name)
            self._stream.time_base = Fraction(1, s.fps)
        except Exception:
            if self._container is not None:
                self._container.close()
            raise

    def write(self, rgb, timestamp_ns=None):
        if self._closed:
            raise RuntimeError("recorder is closed")
        timestamp_ns = time.monotonic_ns() if timestamp_ns is None else timestamp_ns
        if not isinstance(timestamp_ns, int) or timestamp_ns < 0:
            raise ValueError("timestamp_ns must be a nonnegative monotonic integer")
        if self._origin_ns is None:
            self._origin_ns = timestamp_ns
        pts = (timestamp_ns - self._origin_ns) * self.settings.fps // 1_000_000_000
        if pts <= self._last_pts:
            self.frames_dropped += 1
            return False
        av = _dependency("av")
        s = self.settings
        frame = av.VideoFrame.from_ndarray(fit_rgb(rgb, s.width, s.height), format="rgb24")
        frame.pts, frame.time_base = pts, Fraction(1, s.fps)
        for packet in self._stream.encode(frame):
            self._container.mux(packet)
            self.encoded_bytes += packet.size
        self._last_pts = pts
        self.frames_written += 1
        return True

    @property
    def encoded_mbps(self):
        """Average encoded packet bitrate over media time, excluding mux overhead.

        Short captures may report zero until the encoder emits packets. This
        value measures host output and must not be labelled camera/USB bitrate.
        """
        if self._last_pts < 0:
            return 0.0
        duration = (self._last_pts + 1) / self.settings.fps
        return self.encoded_bytes * 8 / duration / 1_000_000

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.frames_written:
                for packet in self._stream.encode(None):
                    self._container.mux(packet)
                    self.encoded_bytes += packet.size
        finally:
            self._container.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


class VirtualCameraSink:
    """Send RGB frames through pyvirtualcam's installed OBS backend.

    OBS virtual camera must already be installed. Only one producer can own it;
    do not also press Start Virtual Camera in OBS. Scheduling belongs to caller.
    Actual Windows application compatibility still requires hardware/OS tests.
    """
    def __init__(self, width=1280, height=720, fps=24, backend="obs"):
        EncodingSettings(width=width, height=height, fps=fps)
        virtualcam = _dependency("pyvirtualcam")
        self.width, self.height = width, height
        self._closed = False
        self._camera = virtualcam.Camera(width=width, height=height, fps=fps, fmt=virtualcam.PixelFormat.RGB, backend=backend)
        self.device = self._camera.device
        self.frames_written = 0

    def write(self, rgb, timestamp_ns=None):
        if self._closed:
            raise RuntimeError("virtual camera is closed")
        self._camera.send(fit_rgb(rgb, self.width, self.height))
        self.frames_written += 1
        return True

    def close(self):
        if not self._closed:
            self._closed = True
            self._camera.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
