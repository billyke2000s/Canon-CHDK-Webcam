"""Validated, versioned user preferences; no device capabilities are implied."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class AppSettings:
    mode: str = "simulate"
    width: int = 640
    height: int = 480
    fps: int = 24
    codec: str = "h264"
    bitrate: int = 30
    virtual_camera: bool = False
    reconnect: bool = True
    low_latency: bool = True
    buffer_size: int = 2
    encoder: str = "auto"
    debug_logging: bool = False
    rotation: int = 0

    def validate(self) -> AppSettings:
        if self.mode not in ("simulate", "usb"):
            raise ValueError("Source must be simulate or usb")
        if any(type(value) is not int for value in
               (self.width, self.height, self.fps, self.bitrate, self.buffer_size)):
            raise ValueError("Video dimensions, rate, bitrate and buffer must be integers")
        if (self.width, self.height) not in ((640, 480), (1280, 720), (1920, 1080)):
            raise ValueError("Unsupported host output dimensions")
        if self.fps not in (15, 24, 30):
            raise ValueError("Host output rate must be 15, 24 or 30 FPS")
        if self.codec not in ("h264", "mjpeg") or not 2 <= self.bitrate <= 60:
            raise ValueError("Use h264 or mjpeg with a target bitrate of 2–60 Mbps")
        if not 1 <= self.buffer_size <= 8:
            raise ValueError("Buffer size must be 1–8 frames")
        if type(self.rotation) is not int or self.rotation not in (0, 90, 180, 270):
            raise ValueError("Rotation must be 0, 90, 180 or 270 degrees")
        if self.encoder not in ("auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf"):
            raise ValueError("Unsupported host encoder preference")
        for name in ("virtual_camera", "reconnect", "low_latency", "debug_logging"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        return self


def default_settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".config"))
    return base / "CanonCHDKWebcam" / "settings.json"


def load_settings(path: Path | str | None = None) -> AppSettings:
    path = Path(path) if path is not None else default_settings_path()
    try:
        with path.open("rb") as handle:
            data = handle.read(65537)
    except FileNotFoundError:
        return AppSettings()
    if len(data) > 65536:
        raise ValueError("Settings file exceeds 64 KiB")
    try:
        payload = json.loads(data)
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Unsupported settings version")
        values = payload.get("settings")
        if not isinstance(values, dict):
            raise ValueError("Missing settings object")
        known = {field.name for field in fields(AppSettings)}
        if set(values) - known:
            raise ValueError("Unknown settings fields")
        return AppSettings(**values).validate()
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid settings file: {exc}") from exc


def save_settings(settings: AppSettings, path: Path | str | None = None) -> None:
    """Replace preferences atomically, retaining the last valid file on failure."""
    settings.validate()
    path = Path(path) if path is not None else default_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({"version": 1, "settings": asdict(settings)}, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
