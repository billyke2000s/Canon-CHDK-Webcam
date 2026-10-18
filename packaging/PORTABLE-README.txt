Canon CHDK Webcam - EXPERIMENTAL Windows portable build

Extract the complete ZIP to a writable folder. Keep _internal beside the EXE.
Launch Canon-CHDK-Webcam.exe. No Python installation is required.
Start with Simulation. Simulation is synthetic and does not verify a camera.

This build has NOT been verified against a physical Canon camera. Native
1080p H.264 extraction is research, not an implemented camera capability.
Selecting 1080p host output scales viewport images; it adds no source detail.

Windows USB capture requires compatible CHDK and a WinUSB/libusb driver for
the camera interface. The bundled libusb DLL is not a Windows USB driver.
Read docs before changing a USB driver; ordinary Canon import can be affected.
OBS Studio's virtual camera must be installed separately for webcam output.
Do not start OBS's own virtual camera while this application owns that output.

See README.md and docs/ for setup, limitations, and hardware validation.
Third-party license texts are in THIRD-PARTY-LICENSES/. Dependencies' native
components retain their own licensing terms, including FFmpeg builds.
Source and issue reports: https://github.com/billyke2000s/Canon-CHDK-Webcam
