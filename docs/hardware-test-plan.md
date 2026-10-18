# Hardware validation checklist

This is a plan for when the IXUS 117 HS is available, not a claim of compatibility.

1. Record exact Canon firmware version and camera USB VID/PID.
2. Verify CHDK build matches that firmware and loads from the SD card.
3. Confirm camera appears over USB and determine whether Windows has claimed it.
4. Connect with an established CHDK PTP client and record protocol version.
5. Capture a sample viewport frame with overlays off and on; document dimensions,
   pixel format, stride, FPS and timestamps.
6. Benchmark 5 minutes of preview with dropped-frame and transfer statistics.
7. Confirm whether movie mode allows concurrent PTP transfers.
8. Study firmware-version-specific encoder buffers read-only before any patching.
9. Test video output with conservative settings and explicit timeout/recovery.
10. Validate host-side virtual camera in OBS and a video calling application.

Do not write undocumented memory addresses, change voltage or thermal settings,
or flash experimental camera firmware. Preserve original firmware and SD data.

## Mode qualification
Every UI option must be marked as confirmed, experimental or unavailable.
1080p24 H.264 and 30 Mbps are **targets**, not yet supported features.
