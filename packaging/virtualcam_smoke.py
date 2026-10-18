"""Mock-free OBS backend smoke test. Does not install/register any software.

Run only on Windows with OBS Virtual Camera installed. The optional independent
DirectShow receiver is isolated in a killable child because device reads may
block forever. Success at sending alone is explicitly weaker than verified
receipt and does not validate Canon capture or application compatibility.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
from pathlib import Path
import platform
from queue import Empty
import time

PALETTE = ((32, 160, 224), (192, 64, 32))


def receive_frames(queue, device, duration):
    """Read actual DirectShow RGB frames; recognize both transmitted colors."""
    import av
    import numpy as np
    count, colors = 0, set()
    try:
        with av.open("video=" + device, format="dshow", options={
            "video_size": "640x480", "framerate": "24", "rtbufsize": "16M",
        }) as capture:
            start = time.monotonic()
            for frame in capture.decode(video=0):
                # Top region stays solid while a moving marker occupies bottom.
                rgb = frame.to_ndarray(format="rgb24")
                sample = rgb[16:48, 16:48].astype(np.float32).mean(axis=(0, 1))
                distance = [float(np.abs(sample - color).max()) for color in PALETTE]
                match = int(np.argmin(distance))
                if distance[match] < 35:
                    colors.add(match)
                count += 1
                if count >= 12 and len(colors) == 2:
                    break
                if time.monotonic() - start > duration:
                    break
        queue.put(dict(status="verified" if len(colors) == 2 and count >= 12 else "content_mismatch",
                       received_frames=count, matched_colors=sorted(colors)))
    except Exception as exc:
        queue.put(dict(status="failed", received_frames=count, error=str(exc)))


def run(seconds=12):
    report = dict(platform=platform.platform(), source="synthetic RGB; no Canon camera",
                  native_send_verified=False, receive_verified=False,
                  limitations="Does not test Discord/Teams/Zoom/browser compatibility or physical USB capture")
    if platform.system() != "Windows":
        report["error"] = "This native OBS smoke test requires Windows"
        return report, 1
    receiver = queue = None
    try:
        import av
        import numpy as np
        import pyvirtualcam
        from canon_webcam.media import VirtualCameraSink

        report.update(pyav=av.__version__, pyvirtualcam=pyvirtualcam.__version__)
        report["dshow_available"] = "dshow" in av.formats_available
        with VirtualCameraSink(640, 480, 24, backend="obs") as sink:
            report["device"] = sink.device
            if report["dshow_available"]:
                context = multiprocessing.get_context("spawn")
                queue = context.Queue()
                receiver = context.Process(target=receive_frames, args=(queue, sink.device, seconds - 2))
                receiver.start()
            else:
                report["receiver"] = dict(status="unsupported", reason="Installed PyAV/FFmpeg build has no DirectShow input")
            rgb = np.empty((480, 640, 3), dtype=np.uint8)
            start = time.monotonic()
            for index in range(seconds * 24):
                rgb[:] = PALETTE[(index // 48) % 2]
                marker = (index * 8) % 600
                rgb[400:450, marker:marker + 40] = 255
                sink.write(rgb, time.monotonic_ns())
                time.sleep(max(0, start + (index + 1) / 24 - time.monotonic()))
            report.update(native_send_verified=True, sent_frames=sink.frames_written)
            if receiver:
                receiver.join(timeout=2)
                if receiver.is_alive():
                    receiver.terminate()
                    receiver.join(timeout=3)
                    report["receiver"] = dict(status="timeout", reason="DirectShow reader did not complete before deadline")
                else:
                    try:
                        report["receiver"] = queue.get(timeout=1)
                    except Empty:
                        report["receiver"] = dict(status="failed", reason=f"Reader exited {receiver.exitcode} without result")
                report["receive_verified"] = report["receiver"]["status"] == "verified"
        # Reopen exercises normal ownership release and cleanup in the real backend.
        with VirtualCameraSink(640, 480, 24, backend="obs") as sink:
            sink.write(rgb, time.monotonic_ns())
        report["reopen_verified"] = True
        if report["dshow_available"] and not report["receive_verified"]:
            return report, 1
        return report, 0
    except Exception as exc:
        report["error"] = str(exc)
        return report, 1
    finally:
        if receiver and receiver.is_alive():
            receiver.terminate()
            receiver.join(timeout=3)
        if queue:
            queue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("virtualcam-report.json"))
    parser.add_argument("--seconds", type=int, default=12)
    parser.add_argument("--require-receive", action="store_true", help="Fail if the installed FFmpeg lacks DirectShow")
    args = parser.parse_args()
    if not 8 <= args.seconds <= 60:
        parser.error("--seconds must be 8..60")
    report, code = run(args.seconds)
    if args.require_receive and not report["receive_verified"]:
        code = 1
    report["success"] = code == 0
    report["validation_level"] = ("received_synthetic_frames" if report["receive_verified"] else
                                  "native_sender_only" if report["native_send_verified"] else "failed")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
