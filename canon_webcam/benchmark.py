"""Headless simulated/USB throughput and bounded-memory soak diagnostics."""
import argparse
import json
import logging
from time import monotonic, sleep
import tracemalloc
from .runtime import CaptureController, CaptureOptions


def run(seconds=60, mode='simulate', recording=None, fps=24):
    if not 0 < seconds <= 86400:
        raise ValueError('duration must be 0..86400 seconds')
    controller = CaptureController(CaptureOptions(mode=mode, recording=recording, fps=fps,
                                                   reconnect=False))
    tracemalloc.start()
    start = monotonic()
    controller.start()
    try:
        while monotonic() - start < seconds:
            controller.poll_frame()
            if controller.snapshot()['state'] == 'error':
                break
            sleep(.02)
    finally:
        controller.stop()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    report = controller.snapshot()
    report.update(elapsed_seconds=monotonic() - start,
                  python_current_bytes=current, python_peak_bytes=peak,
                  queued_frames=controller._frames.qsize(),
                  simulated=(mode == 'simulate'),
                  hardware_verified=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--mode', choices=['simulate', 'usb'], default='simulate')
    parser.add_argument('--recording')
    parser.add_argument('--fps', type=int, choices=[10, 15, 24, 30], default=24)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)
    report = run(args.seconds, args.mode, args.recording, args.fps)
    print(json.dumps(report, indent=2))
    return int(report['state'] == 'error')


if __name__ == '__main__':
    raise SystemExit(main())
