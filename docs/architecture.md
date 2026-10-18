# Architecture

The stable host path is USB PTP → CHDK viewport → NumPy RGB conversion and display geometry → bounded capture queue → optional PyAV recorder / pyvirtualcam sink → latest-only GUI preview. The camera returns display pixels; host output size, codec and bitrate are separate settings.

`usb.py` discovers Canon USB devices and claims only a still-image/PTP bulk interface. `ptp.py` implements standard PTP session lifecycle, DeviceInfo and CHDK version/GetDisplayData requests. It does not execute scripts, read arbitrary memory or alter movie configuration. Command availability comes from DeviceInfo; CHDK subcommands are selected using documented protocol versions, not a fictional discovery operation.

`liveview.py` parses checked descriptors, excludes bitmap overlays, decodes format-specific chroma and corrects non-square display pixels. Raw dimensions remain diagnostics; preview dimensions reflect display correction. Orientation is an explicit user setting because CHDK descriptors contain no orientation metadata. Timestamps are monotonic **host receipt** timestamps, not sensor capture times.

`runtime.py` owns two workers. The acquisition worker connects, requests and decodes frames with finite USB deadlines, then puts them in a queue limited to 1–8 frames. On congestion it discards the oldest frame. The output worker encodes/outputs frames and keeps a single latest preview. Errors become status messages; stop signals workers and joins with a finite timeout. Failed PTP transactions require a new session. Reconnection uses serial identity when readable; otherwise the original USB address is retained to avoid switching devices.

`media.py` uses FFmpeg through PyAV. The software H.264 baseline is libx264; explicitly selected hardware encoders are probed before file creation and fall back if unavailable. Files preserve elapsed monotonic time, including dropped-frame gaps. The virtual camera sends RGB to an installed OBS backend; an H.264 recording setting does not configure camera-side encoding or virtual-device compression.

`gui.py` keeps all Tk operations on the main thread; lifecycle calls run in background threads and return events. `settings.py` validates bounded versioned JSON and atomically replaces preferences. Debug logs and source/output statistics aid hardware qualification.

Original `stream.py`, `simulator.py`, `inspect.py`, `mjpeg.py` and `diagnostics.py` remain independent offline CWCM research utilities. They are not substituted for CHDK's protocol. Native camera H.264 extraction is a separate gated experiment, not a source option.

Known limits: source operations are paced at a requested maximum, not guaranteed source FPS; no sensor clock synchronization is possible from ordinary live-view responses; frozen webcam frames during USB outages depend on the virtual backend; indefinite native codec hangs cannot be forcibly cancelled from a Python thread. A worker that exceeds shutdown timeout is reported as an error; restart the application before retrying.
