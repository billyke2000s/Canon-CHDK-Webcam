# Canon CHDK USB Webcam

Experimental open-source webcam bridge for the **Canon IXUS 117 HS / PowerShot ELPH 100 HS**.

## Goals
- Clean live preview over CHDK PTP USB
- Windows virtual-camera output
- 1080p24 H.264 at selectable bitrate (30 Mbps preferred) **if camera encoder access proves possible**
- MJPEG fallback **if camera-side encoding is feasible**
- Diagnostics for frame size, throughput and latency

## Reality check
CHDK's ordinary live view transfers a **display viewport**, not the full-resolution recording stream. The native H.264 stream is **not implemented or demonstrated**. USB bandwidth alone does not establish camera firmware support.

## Current state
This repository starts with a host-side configuration model and offline diagnostics. Hardware-dependent features are tracked as experiments, not advertised as working.

## Getting started
```bash
python -m unittest discover -s tests -v
python -m canon_webcam.cli --codec h264 --bitrate 30 --resolution 1920x1080 --fps 24
```
Python 3.10+; standard library only for the initial tools.

## Safety
CHDK normally loads from the SD card without replacing the camera's permanent firmware. Do not flash unknown firmware images or write arbitrary camera memory addresses. Confirm firmware revision and back up the SD card before camera-side experiments.

## Roadmap
1. Confirm CHDK port / firmware revision and PTP compatibility.
2. Implement transport and viewport decoding; benchmark clean preview.
3. Reverse engineer the movie encoder and buffer lifetime in a firmware-version-specific, read-only way.
4. Prototype bounded frame transfer, flow control and recovery.
5. Add a Windows virtual-camera backend and settings UI.
6. Validate codec, resolution, framerate and bitrate against physical hardware.

Contributions and documented test captures welcome.
