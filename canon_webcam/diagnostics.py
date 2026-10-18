"""Offline stream diagnostics; no physical camera required."""
from collections import deque
from dataclasses import dataclass
from statistics import mean
from time import monotonic


@dataclass(frozen=True)
class Snapshot:
    frames: int
    dropped: int
    fps: float
    bitrate_mbps: float
    last_sequence: int | None


class StreamMetrics:
    def __init__(self, window_seconds=5.0, clock=monotonic):
        if window_seconds <= 0:
            raise ValueError("window must be positive")
        self.window = window_seconds
        self.clock = clock
        self.samples = deque()
        self.frames = 0
        self.dropped = 0
        self.last_sequence = None

    def observe(self, packet):
        now = self.clock()
        if self.last_sequence is not None:
            delta = (packet.sequence - self.last_sequence) & 0xFFFFFFFF
            if 0 < delta < 0x80000000:
                self.dropped += max(0, delta - 1)
        self.last_sequence = packet.sequence
        self.frames += 1
        self.samples.append((now, len(packet.payload)))
        self._prune(now)

    def _prune(self, now):
        while self.samples and self.samples[0][0] < now - self.window:
            self.samples.popleft()

    def snapshot(self):
        now = self.clock()
        self._prune(now)
        if not self.samples:
            return Snapshot(self.frames, self.dropped, 0.0, 0.0, self.last_sequence)
        elapsed = max(0.001, min(self.window, now - self.samples[0][0]))
        fps = max(0, len(self.samples) - 1) / elapsed
        bitrate = sum(size for _, size in self.samples) * 8 / elapsed / 1_000_000
        return Snapshot(self.frames, self.dropped, fps, bitrate, self.last_sequence)
