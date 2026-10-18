# Canon CHDK Webcam

Experimental Windows webcam bridge for **Canon IXUS 117 HS / PowerShot ELPH 100 HS**. Continues the original configuration, offline packet tools and viewport decoder.

**No physical Canon has been tested with this application. Native 1080p24 H.264 extraction is research, not an implemented camera mode.** Standard CHDK live view transfers a display viewport. Selecting 1080p host output scales that viewport; it does not recover recorded-video detail. The camera's 1080p60 mode does not exist.

## Feature status

| Feature | Implementation | Verification |
|---|---|---|
| Standard PTP session, DeviceInfo, CHDK version negotiation | Implemented via PyUSB/libusb | Mock USB tests only |
| Continuous clean viewport requests, timeout/reconnect | Implemented; GetDisplayData command 12 | Synthetic integration; physical camera pending |
| YUV8/YUV8B/YUV8C, padding, margins, display aspect, rotation | Implemented NumPy conversion | Synthetic/reference comparison |
| H.264/MJPEG host recording, bitrate 2–60 Mbps, selectable output size/FPS | Implemented PyAV/FFmpeg | Real local encode/decode tests on synthetic images |
| Hardware host encoders | Explicit NVENC/QSV/AMF preference with software fallback | Unavailable-encoder fallback tested; GPU validation pending |
| Windows virtual webcam | pyvirtualcam OBS backend adapter | Mock sink tested; actual Windows applications pending |
| GUI, preview, preferences, diagnostics | Implemented Tk/Pillow | Headless application smoke; desktop validation tracked in CI |
| Windows portable packaging | PyInstaller and Windows Actions workflow | Check latest Actions results before download |
| Native camera H.264/MJPEG over USB | **Not implemented** | No evidence of working extraction |
| Firmware research / compatibility gates | Offline source inventory and gated plan | No camera patch or permanent firmware modification |

## Windows installation

1. Open [Actions](https://github.com/billyke2000s/Canon-CHDK-Webcam/actions) and select a **successful** `Test, package, and experimental release` run. Download `windows-x64-experimental` under Artifacts. If the run failed or is still running, no verified portable build is available from that run.
2. Extract both archive layers into a writable folder. Keep the whole `Canon-CHDK-Webcam` directory, including `_internal`; launch `Canon-CHDK-Webcam.exe`.
3. Start with **Simulation (synthetic frames)**. Connect & start capture should show a moving test chart. This checks the application, not your camera.
4. Install OBS Studio separately if webcam output is needed. Enable **Output to OBS virtual camera** here; do not simultaneously start the virtual camera in OBS. Select **OBS Virtual Camera** in Discord, Teams, Zoom or your browser. Actual application compatibility still needs Windows testing.
5. For real capture, follow [USB/PTP setup](docs/ptp.md), install an exact-firmware CHDK build from its official sources, and select **USB camera**. You may need WinUSB/libusb-compatible Windows drivers on the camera's PTP interface. Driver changes can affect ordinary photo transfer; record the original driver so you can restore it.

The application does not install CHDK, replace your USB driver, switch camera recording mode, or patch firmware automatically. See the [physical validation procedure](docs/hardware-test-plan.md).

## Using the app

Choose source, **host output** size and FPS, recording codec, target bitrate, encoder preference and queue size before starting. A two-frame queue is the default; old frames are discarded when output cannot keep up. Actual source dimensions and measured FPS/USB payload rate appear below the preview. Higher bitrate is not a guarantee of higher image quality or actual encoded bitrate.

Recording is optional: choose an MKV file, enable recording and start capture. H.264 can also use MP4; MKV is recommended for MJPEG and experiments. Stop capture to finalize the file. Webcam output uses uncompressed RGB frames; recording codec/bitrate settings apply to the file, not the Windows virtual device.

Clean capture requests the viewport alone, excluding CHDK bitmap planes. Canon overlays baked into the viewport, movie-mode/PTP concurrency, true frame cadence, and camera-specific geometry must be checked on hardware. No exposure/ISO/focus controls are exposed without capability evidence.

## Run from source

Python 3.10+ with Tk support (included in the standard Windows Python installer):

```sh
python -m pip install -r requirements-desktop.txt -e .
python -m canon_webcam.gui
python -m canon_webcam.gui --self-test --report self-test.json
python -m unittest discover -s tests -v
python -m canon_webcam.benchmark --seconds 60 --recording simulated.mkv
```

USB benchmark, only after camera/driver setup:

```sh
python -m canon_webcam.benchmark --mode usb --seconds 300 --debug
```

Existing `canon-webcam-config`, `canon-webcam-simulate` and `canon-webcam-inspect` commands remain available. CWCM files are experimental offline envelopes, **not CHDK PTP packets or playable encoded footage**.

## Documentation

- [Architecture and worker lifecycle](docs/architecture.md)
- [USB protocol and driver troubleshooting](docs/ptp.md)
- [Live-view formats and display geometry](docs/chdk-liveview.md)
- [Host encoders and OBS virtual camera](docs/video-output.md)
- [Firmware research and evidence](docs/firmware-research.md)
- [Development, checks and packaging](docs/development.md)
- [Hardware validation and recovery](docs/hardware-test-plan.md)
- [Local validation results and remaining work](docs/validation.md)

## Safety and scope

CHDK normally boots reversibly from the SD card rather than replacing permanent firmware. Confirm the exact camera firmware revision and preserve the original SD card contents. There is no verified encoder-address configuration in this project; native extraction is disabled. Never apply arbitrary addresses from another camera or firmware revision.
