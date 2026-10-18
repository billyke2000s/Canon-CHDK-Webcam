# Physical camera validation and recovery

This procedure is pending; it does not assert camera compatibility. Keep logs and evidence per exact firmware revision. Do not distribute a camera-specific patch or claim native output based on simulation.

## 1. Baseline and reversible setup

1. Photograph the model label and obtain the exact Canon firmware version using an established CHDK identification method. Record USB VID/PID, CHDK build revision, OS version, USB driver, SD card and power source.
2. Back up the SD card. Confirm an official CHDK build explicitly supports that Canon firmware and regional model alias. Install CHDK using its official instructions; retain a card without CHDK for recovery. Never flash unknown firmware.
3. Start the camera normally with the untouched card first. Verify still capture and 1080p24 recording. Do not assume its recording capabilities imply PTP streaming support.
4. Boot CHDK, enable supported USB/PTP operation as required by that build, and connect a reliable USB data cable directly to a Windows port. Avoid a hub for baseline tests. Record negotiated USB speed using a USB descriptor/viewer tool; the host application does not infer High-Speed from throughput.
5. Record the original Windows driver before binding a compatible WinUSB/libusb driver to the camera interface. Do not replace unrelated device drivers. Validate DeviceInfo, CHDK protocol version, serial identity and clean viewport requests using this app and compare with an established CHDKPTP client (one client at a time).

## 2. Viewport qualification

1. Save a raw GetDisplayData(flags=1) response through a developer harness or established CHDKPTP tool. Capture separate metadata: host time, mode, firmware and CHDK version. Do not save CWCM and label it a CHDK response.
2. Compare decoded color bars/scene with the LCD and a still photograph: full-range black/white, signed chroma, padding, active dimensions, margins, non-square pixel correction and orientation. Test 4:3 and widescreen modes separately. Check whether Canon burns any overlays into viewport pixels; bitmap exclusion cannot remove those.
3. Measure actual changing images rather than assuming every request supplies a new sensor frame. Record source size, request cadence, effective unique-frame FPS, payload bitrate and dropped output frames.
4. Run 5 minutes of preview, then a 30-minute recording/virtual-camera soak. Monitor Windows working set, native memory, CPU, latency, camera temperature and power stability. Tracemalloc alone excludes parts of native allocations. Stop on unusual behavior.
5. Unplug and replug during capture, stop/start repeatedly, test stale/changed USB addresses and unavailable drivers. Confirm serial-based reconnection never silently selects another camera. Devices without readable serial may require stopping and reselecting the source.

## 3. Host output qualification

1. Record MKV H.264 and MJPEG at each host output size. Decode with an independent player/ffprobe and verify timestamps, aspect, color and finalization after a normal stop. Do not interpret scaled 1920×1080 as native capture.
2. Test each available hardware encoder preference and software fallback; compare measured rather than requested bitrate. MJPEG bitrate is a target and may not track slider values tightly.
3. Install OBS, enable virtual output in this application, and select OBS Virtual Camera in OBS capture, Discord, Teams, Zoom and browser getUserMedia. Test frame rates and application restarts; one producer owns the OBS backend at a time.
4. Repeat after USB interruption and OBS/backend errors. Document whether consumers retain a frozen frame during an outage. Measure glass-to-glass latency with a visible clock or LED reference, not host receipt timestamps alone.

## 4. Native movie pipeline experiments

Read the firmware research document first. Ordinary host capture never executes arbitrary scripts or accesses memory.

1. Obtain matching upstream source and a legally obtained firmware dump from the actual device if needed; hash and retain them privately. Resolve firmware identity and signatures before generating any experimental build.
2. Build the **unmodified** matching CHDK port using its documented toolchain; confirm its ordinary behavior before instrumentation. There is no ready-to-flash native-streaming image in this repository.
3. Start with existing Canon recording and passive, bounded logging of task transitions. Do not assume movie task locals are stable encoder packet pointers. Prove encoded-buffer ownership, bounds, lifetime, cache behavior, keyframes/SPS/PPS and timestamps with trace evidence.
4. Establish whether PTP requests operate during normal SD movie recording, initially at conservative existing settings. Do not bypass SD callbacks or alter the encoder without a recoverable, revision-specific design.
5. Only after ownership evidence exists design bounded copying/reference release and USB queue backpressure. Dropping arbitrary H.264 packets corrupts dependent frames; define recovery to the next IDR and parameter sets. SD and USB consumers must not race to release a buffer.
6. Validate optional packet routing, then independent decode at native source dimensions. Determine whether SD writes are mandatory before considering recording without a card/file. Measure safe bitrate range on the exact mode and firmware; do not equate CHDK's quality scale with Mbps.

## Recovery

For an application error, stop capture, wait for finite USB timeout/recording finalization, close other PTP/OBS producers, power-cycle the camera if needed and restart the app. If the camera stops responding, disconnect USB and power, remove the CHDK card, insert the preserved normal card and boot normally. Restore the original Windows driver to recover ordinary photo transfer if needed. Keep diagnostics at `%LOCALAPPDATA%/CanonCHDKWebcam/logs/canon-webcam.log`; review serial numbers and paths before sharing logs publicly.
