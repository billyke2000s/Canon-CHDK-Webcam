"""Bounded capture and output workers. Camera source is always CHDK viewport.

USB reads and conversion never run on the GUI thread. Slow sinks drop queued
frames rather than accumulating latency; timestamps are host receipt times.
"""
from dataclasses import dataclass
import logging
from queue import Queue, Empty, Full
from threading import Event, Lock, Thread
from time import monotonic, monotonic_ns

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureOptions:
    mode: str = 'simulate'
    width: int = 640
    height: int = 480
    fps: int = 24
    codec: str = 'h264'
    bitrate: int = 30
    recording: str | None = None
    virtual_camera: bool = False
    reconnect: bool = True
    low_latency: bool = True
    buffer_size: int = 2
    encoder: str = 'auto'
    rotation: int = 0

    def validate(self):
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError('invalid rotation')
        if self.mode not in ('simulate', 'usb'):
            raise ValueError('source must be simulate or usb')
        if (self.width, self.height) not in ((640, 480), (1280, 720), (1920, 1080)):
            raise ValueError('invalid host output size')
        if self.fps not in (10, 15, 24, 30) or not 2 <= self.bitrate <= 60:
            raise ValueError('invalid host frame rate or bitrate')
        if self.codec not in ('h264', 'mjpeg') or not 1 <= self.buffer_size <= 8:
            raise ValueError('invalid codec or buffer size')
        return self


@dataclass(frozen=True)
class CapturedFrame:
    rgb: object
    width: int
    height: int
    timestamp_ns: int
    source_width: int = 0
    source_height: int = 0


class SimulatedSource:
    """Moving RGB test chart; never advertised as a connected Canon."""
    def connect(self):
        return None

    def read(self):
        import numpy as np
        t = monotonic_ns()
        x = np.arange(640, dtype=np.uint16)[None, :]
        y = np.arange(480, dtype=np.uint16)[:, None]
        rgb = np.empty((480, 640, 3), dtype=np.uint8)
        rgb[:, :, 0] = (x + t // 30_000_000) % 256
        rgb[:, :, 1] = y % 256
        rgb[:, :, 2] = (x // 2 + y // 2) % 256
        return CapturedFrame(rgb, 640, 480, t), rgb.nbytes

    def close(self):
        pass


class USBSource:
    def __init__(self, rotation=0):
        self.rotation = rotation
        self.camera = None
        self.identity = None

    def connect(self):
        from .usb import discover_cameras, PyUSBTransport
        from .ptp import CHDKCamera
        if self.identity is None:
            devices = discover_cameras()
            if len(devices) != 1:
                raise RuntimeError('Connect exactly one Canon PTP camera; found %d' % len(devices))
            self.identity = devices[0]
        self.camera = CHDKCamera(PyUSBTransport.open(self.identity))
        try:
            info = self.camera.connect()
            log.info('Connected camera: %s', info)
        except Exception:
            self.close()
            raise

    def read(self):
        from .liveview import parse_viewport, normalize_rgb
        data = self.camera.get_live_view(flags=1)
        timestamp = monotonic_ns()
        view = parse_viewport(data)
        rgb = normalize_rgb(view, self.rotation)
        return CapturedFrame(rgb, rgb.shape[1], rgb.shape[0], timestamp,
                             view.width, view.height), len(data)

    def close(self):
        if self.camera:
            try:
                self.camera.close()
            finally:
                self.camera = None


class CaptureController:
    def __init__(self, config: CaptureOptions, source_factory=None, recorder_factory=None,
                 virtual_factory=None):
        self.config = config.validate()
        self._source_factory = source_factory or (SimulatedSource if config.mode == 'simulate' else lambda: USBSource(config.rotation))
        self._recorder_factory = recorder_factory
        self._virtual_factory = virtual_factory
        self._stop = Event()
        self._done = Event()
        self._lock = Lock()
        self._frames = Queue(config.buffer_size)
        self._preview = Queue(1)
        self._threads = []
        self._stats = dict(state='idle', error='', frames=0, dropped=0, fps=0.0,
                           usb_mbps=0.0, source_width=0, source_height=0,
                           output_width=config.width, output_height=config.height,
                           reconnects=0, virtual_camera=False, recording=False,
                           output_dropped=0, encoder='', encoded_mbps=0.0, encoder_fallback='', firmware='', protocol='')

    def _set(self, **values):
        with self._lock:
            self._stats.update(values)

    def snapshot(self):
        with self._lock:
            return dict(self._stats)

    def start(self):
        if any(t.is_alive() for t in self._threads):
            raise RuntimeError('capture already running')
        self._stop.clear()
        self._done.clear()
        for q in (self._frames, self._preview):
            while not q.empty():
                q.get_nowait()
        self._set(state='connecting', error='', frames=0, dropped=0, fps=0.0,
                  usb_mbps=0.0, reconnects=0)
        self._threads = [Thread(target=self._acquire, daemon=True),
                         Thread(target=self._output, daemon=True)]
        for thread in self._threads:
            thread.start()

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=6)
        if any(t.is_alive() for t in self._threads):
            message = 'Capture/output did not stop within timeout; retry Stop or restart the application'
            self._set(state='error', error=message)
            raise RuntimeError(message)
        elif self.snapshot()['state'] != 'error':
            self._set(state='stopped')

    def poll_frame(self):
        try:
            return self._preview.get_nowait()
        except Empty:
            return None

    def _latest(self, queue, frame, count_drop=False):
        try:
            queue.put_nowait(frame)
        except Full:
            try:
                queue.get_nowait()
                if count_drop:
                    with self._lock:
                        self._stats['dropped'] += 1
            except Empty:
                pass
            queue.put_nowait(frame)

    def _acquire(self):
        source = None
        start, total, count = monotonic(), 0, 0
        retries = 0
        try:
            source = self._source_factory()
            while not self._stop.is_set():
                try:
                    source.connect()
                    if self._stop.is_set():
                        break
                    self._set(state='streaming', error='')
                    if isinstance(source, USBSource):
                        self._set(firmware=source.camera.device_info.firmware_version,
                                  protocol='.'.join(map(str, source.camera.protocol_version)))
                    while not self._stop.is_set():
                        tick = monotonic()
                        frame, size = source.read()
                        total += size
                        count += 1
                        elapsed = max(.001, monotonic() - start)
                        self._set(frames=count, fps=count / elapsed,
                                  usb_mbps=(total * 8 / elapsed / 1e6 if self.config.mode == 'usb' else 0),
                                  source_width=frame.source_width or frame.width,
                                  source_height=frame.source_height or frame.height)
                        self._latest(self._frames, frame, True)
                        self._stop.wait(max(0, 1 / self.config.fps - (monotonic() - tick)))
                except Exception as exc:
                    log.exception('Capture connection failed')
                    self._set(error=str(exc))
                    if not self.config.reconnect:
                        raise
                    retries += 1
                    self._set(state='reconnecting', reconnects=retries)
                finally:
                    try:
                        source.close()
                    except Exception:
                        log.exception('Source cleanup failed')
                if not self._stop.is_set():
                    self._stop.wait(min(5, .5 * 2 ** min(retries, 4)))
        except Exception as exc:
            self._set(state='error', error=str(exc))
            self._stop.set()
        finally:
            self._done.set()

    def _output(self):
        recorder = virtual = None
        try:
            if self.config.recording:
                from .media import EncodingSettings, VideoRecorder
                settings = EncodingSettings(width=self.config.width, height=self.config.height,
                    fps=self.config.fps, codec=self.config.codec, bitrate_mbps=self.config.bitrate,
                    encoder=self.config.encoder, low_latency=self.config.low_latency)
                recorder = (self._recorder_factory or VideoRecorder)(self.config.recording, settings)
                self._set(recording=True, encoder=getattr(recorder, 'encoder_name', 'test'),
                          encoder_fallback=getattr(recorder, 'fallback_reason', '') or '')
            if self.config.virtual_camera:
                from .media import VirtualCameraSink
                virtual = (self._virtual_factory or VirtualCameraSink)(
                    self.config.width, self.config.height, self.config.fps)
                self._set(virtual_camera=True)
            while not self._stop.is_set():
                try:
                    frame = self._frames.get(timeout=.1)
                except Empty:
                    if self._done.is_set():
                        break
                    continue
                if recorder:
                    recorder.write(frame.rgb, frame.timestamp_ns)
                    self._set(output_dropped=getattr(recorder, 'frames_dropped', 0),
                              encoded_mbps=getattr(recorder, 'encoded_mbps', 0.0))
                if virtual:
                    virtual.write(frame.rgb, frame.timestamp_ns)
                self._latest(self._preview, frame)
        except Exception as exc:
            log.exception('Output failed')
            self._set(state='error', error=str(exc))
            self._stop.set()
        finally:
            for sink in (recorder, virtual):
                if sink:
                    try:
                        sink.close()
                    except Exception as exc:
                        log.exception('Output finalization failed')
                        self._set(state='error', error=str(exc))
            self._set(recording=False, virtual_camera=False)
