# Architecture and research notes

## Stage A: existing CHDK viewport
CHDK PTP live view obtains a display-oriented viewport and optional overlay buffers. We must measure actual format, dimensions, frame cadence and USB throughput on the IXUS 117 HS. A clean viewport is not proof of 1080p video.

## Stage B: full-resolution recording path (unproven)
Find camera-firmware-version-specific movie buffer ownership, encoder entry points, encoded packet boundaries, timestamps and safe backpressure. Prefer passive instrumentation before modifying the pipeline. Recording mode may require SD writes or additional state transitions. Never assume a 30 Mbps setting is accepted by the native encoder.

## Stage C: USB transport
A normal CHDK PTP request-response exchange may not sustain low-latency video; benchmark first. Any custom transfer must provide frame framing, timestamps, bounded buffering, reconnects and drop policy.

## Stage D: Windows camera
Initially bridge received frames to a virtual camera using a documented Windows-compatible backend. H.264 and MJPEG selection must distinguish camera-side encoding from host-side transcoding. UI must expose only tested modes.

## Device verification checklist
- Camera firmware revision
- CHDK boot and PTP extension version
- USB High Speed negotiation
- Viewport dimensions and pixel layout
- Camera record-mode 1080p24 behavior
- Encoder buffer accessibility and safety
- Sustained bitrate and thermal behavior
