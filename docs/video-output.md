# Host encoding and Windows webcam output

The stable source is CHDK's viewport. Its actual dimensions come from the
live-view response, not the output selector. Producing a 1920 × 1080 file or
virtual camera from a smaller viewport is **upscaling**, not native 1080p.
Neither this module nor the OBS backend extracts Canon's recorded H.264 stream.

## Installation

Install the project's media dependencies (PyAV and NumPy) for recording, and
pyvirtualcam for webcam output. Windows packages should bundle these dependencies.
PyAV wheels include FFmpeg libraries; no FFmpeg command-line installation is
required. Optional imports are lazy: USB transport and protocol tests can run
without media packages installed.

For webcam output, install current OBS Studio on Windows and its Virtual Camera
component. Close applications currently using the virtual camera before starting
this application. Select **OBS Virtual Camera** in Discord, Teams, Zoom or the
browser's camera picker. Grant the browser camera permission where required.

The application uses pyvirtualcam to feed the OBS device directly. Do not also
start OBS's own virtual camera producer at the same time. This integration does
not install a new driver or claim to implement a native Media Foundation camera.
Its contract is covered by mocked tests and a separate Windows native OBS
send/DirectShow receive CI test using synthetic frames. Conferencing application
compatibility still needs validation. An unavailable backend produces an actionable error
rather than silently substituting a camera.

## Recording

`canon_webcam.media.VideoRecorder` is a synchronous frame sink with deterministic
cleanup and standard container output. The capture service owns its worker and
bounded queues. The sink never accumulates a Python frame queue.

```python
from canon_webcam.media import EncodingSettings, VideoRecorder

settings = EncodingSettings(
    width=1280, height=720, fps=24,
    codec="h264", bitrate_mbps=30, encoder="auto", low_latency=True,
)
with VideoRecorder("capture.mkv", settings) as recording:
    # rgb is an H × W × 3 uint8 NumPy array; the timestamp is monotonic ns.
    recording.write(rgb, timestamp_ns)
```

Use `.mkv` for H.264 or MJPEG, `.mp4` for H.264, or `.avi` for MJPEG.
Container/codec combinations unsupported by FFmpeg raise an error. The recorder
flushes delayed codec packets and closes the container on normal shutdown and
when the capture caller raises an exception. A crash or power loss can still
leave an incomplete file; MKV is preferable for long captures.

Settings describe **host** encoding:

| Setting | Behavior |
|---|---|
| H.264 | FFmpeg libx264 software encoder by default |
| MJPEG | FFmpeg MJPEG software encoder, full-range YUV420 |
| Bitrate | 2–60 Mbps encoder target; actual output depends on content/codec |
| Dimensions | Even dimensions from 16 to 4096; aspect preserved with black padding |
| Frame rate | Host pacing target 1–60 FPS; never a claimed camera recording mode |
| Low latency | No B frames; libx264 `veryfast`, optional `zerolatency`; NVENC low latency options |
| Hardware | Explicit `h264_nvenc`, `h264_qsv` or `h264_amf`; codec open is probed |
| Fallback | Failed hardware initialization selects libx264 and exposes `fallback_reason` |

`auto` intentionally chooses the predictable software baseline. Hardware encoding
requires the matching GPU and drivers and remains unverified on Windows here.
Failures occurring after initialization propagate to the capture service so the
user can stop/restart recording; the implementation does not splice incompatible
encoder streams into an existing container.

Source timestamps determine relative presentation times. Excess frames in the
same output tick and backwards timestamps are dropped. Gaps remain gaps: the
encoder does not fabricate extra camera frames. Frame counters expose accepted
and dropped frames. Since the encoder runs synchronously, the capture service
must keep UI work separate and drop stale queued frames under sustained load.

## Virtual camera

```python
from canon_webcam.media import VirtualCameraSink

with VirtualCameraSink(width=1280, height=720, fps=24) as webcam:
    webcam.write(rgb, timestamp_ns)
```

The capture worker schedules calls using a monotonic clock. pyvirtualcam's backend
owns virtual-device timestamp delivery; `timestamp_ns` is accepted for the shared
sink interface but is not passed as a device timestamp. Sending to the virtual
camera uses raw RGB, independent of the selected recording codec/bitrate.
The feed is scaled and letterboxed with the same FFmpeg conversion as recording.
The sink does not call `sleep_until_next_frame`, because the capture service owns
pacing and shutdown.

## Evidence and remaining validation

Automated tests encode and decode synthetic H.264 and MJPEG files using real PyAV,
check decoded dimensions and approximate color, preserve timestamp gaps, exercise
hardware-initialization fallback and cleanup, and verify the pyvirtualcam API with
a mocked OBS device. The separate `Experimental Windows native virtual camera` workflow installs
a hash-pinned official OBS component on an ephemeral runner and exercises real
native sending, independent DirectShow reception when supported, content checks
and device reopening. The recorded validation level distinguishes actual receive
verification from sender-only operation. These checks do not validate Canon USB
capture, native Canon video extraction, physical GPU encoders or conferencing
application compatibility.

On Windows, verify preview and source dimensions first, then run OBS Virtual
Camera through each target application for at least 30 minutes. Check connection
loss/recovery, camera ownership conflicts, closing the app while recording,
resolution changes between sessions, and sustained frame/memory counters. Record
both codecs, reopen the files, and compare duration and frame timestamps to the
capture diagnostics. Keep hardware evidence separate from simulated test results.
