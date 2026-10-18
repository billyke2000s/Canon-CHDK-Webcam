# Validation record

Results below are development evidence, not physical-camera support claims.

## Baseline audit

Original commit `594bde6`: 20 tests, one failure. The MJPEG delimiter implementation and fixtures used literal escaped text instead of JPEG marker bytes. Corrected to actual binary SOI/EOI markers. Existing configuration, CWCM parser and offline tools retained. Original protocol notes incorrectly called GetDisplayData subcommand 4; upstream command is 12.

## Local Linux validation

- Real PyAV synthetic-image H.264/MJPEG roundtrip tests verify playable media, dimensions, frame counts and timestamp gaps.
- Synthetic USB integration feeds fragmented PTP bytes through the real CHDK session, viewport decoder and video recorder.
- One 60-second simulated 640×480/24 FPS H.264 recording: 1,428 acquired frames, about 23.8 FPS, zero capture queue drops, one encoding cadence drop; tracemalloc peak approximately 11.5 MB. Encoded bitrate about 7.4 Mbps despite a 30 Mbps target, illustrating that target bitrate is not a measured guarantee.
- Five-minute simulated recording: 7,169 acquired frames, about 23.9 FPS, zero capture queue drops, one encoding cadence drop, approximately 11.5 MB tracemalloc peak. This is synthetic scheduling/encoding evidence, not USB throughput.
- Windows Python 3.10/3.12 and Linux matrix passed at commit `497a16d`; frozen Windows executable passed real H.264/MJPEG simulation and rendered a working GUI preview. Screenshot/report are attached to that Actions run.
- Native Windows CI at `e1303f4` installed a hash-pinned official OBS component on its ephemeral runner, sent 288 synthetic frames through the actual OBS backend, independently received 41 DirectShow frames and verified both transmitted colours. Device close/reopen also passed. [Native validation run](https://github.com/billyke2000s/Canon-CHDK-Webcam/actions/runs/39167728947). This does not verify physical USB capture or consumer conferencing applications.
- Isolated-container libusb can load its shared library but cannot initialize a physical USB bus. Simulation checks dynamic linkage; real-device enumeration requires a suitable host.

The final suite contains 79 host tests and 3 offline firmware tests. The five-minute file independently decoded to 7,168 frames with strictly increasing timestamps over 299.625 seconds. Windows checks and downloadable artifact status are recorded in GitHub Actions. Native process memory and long-duration thermal behavior require separate qualification.

## Not verified

Physical Canon USB capture; exact firmware revision; CHDK record/playback mode; camera-specific viewport dimensions/aspect/overlays/cadence; Windows driver binding; hardware H.264 encoder availability; OBS/Discord/Teams/Zoom/browser interoperability; sustained camera power/temperature; movie recording concurrent with PTP; native encoded-video extraction. No camera-side streaming patch is enabled.
