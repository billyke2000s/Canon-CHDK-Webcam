# Native encoded video: evidence and next experiments

Status: **research only; native USB H.264 extraction is not implemented or
hardware verified**. The host viewport pipeline must remain labelled as
viewport capture, including when host encoded or resized to 1920×1080.

## Camera-specific upstream evidence

The CHDK source port is **`ixus115_elph100hs`**, despite the target's regional
IXUS 117 HS name. The inspected source tree contains revision directories
100c, 101a, 101b and 101c; this is a source inventory, not verification that
the user's camera has any particular revision. The exact camera build,
firmware string and CHDK platform must be identified before loading CHDK.

Research snapshot: CHDK Git mirror commit
`ad402e1b2049662594ccc7d15a9a507138b59079`.

| Upstream file under `trunk/platform/ixus115_elph100hs/` | Evidence | What this does not establish |
|---|---|---|
| `platform_camera.h` | `CAM_VIDEO_QUALITY_ONLY=1`, `CAM_VIDEO_CONTROL` undefined | No direct target-bitrate control; 2–60 Mbps is not supported by this evidence |
| `sub/movie_rec_hdr.c` | `change_video_tables` is a no-op; `set_quality` maps configured 1–99 to Canon quality values +12 through −17 | Quality control is not fixed bitrate or encoder-output redirection |
| `sub/101a/movie_rec.c` | `movie_record_task` receives a message queue, invokes an indirect Canon routine, then calls CHDK `set_quality`; extended-time code references `MovWriter.c` | Callback ownership, encoded buffer layout and lifetime are unresolved |
| `lib.c` | Rotating viewport buffers; video uses three of the four buffers; record viewport dimensions vary by aspect | These are display buffers, not full-resolution sensor frames or encoded H.264 packets |
| `sub/101c/makefile.inc` | 101c uses 101b source with a target-firmware override | ROM CRC differs; do not treat firmware revisions as interchangeable |
| `sub/*/firmware_crc_data.h` | Per-revision ROM/data CRC blocks and version string location | Source matching does not authorize memory writes or prove the camera is healthy |

[Browse pinned camera source](https://github.com/petabyt/chdk/tree/ad402e1b2049662594ccc7d15a9a507138b59079/trunk/platform/ixus115_elph100hs)
and [CHDK core PTP handler](https://github.com/petabyt/chdk/blob/ad402e1b2049662594ccc7d15a9a507138b59079/trunk/core/ptp.c).
These are source observations rather than claims derived from successful
camera runs. Canon hardware H.264 recording does not by itself expose a
compressed live stream over the existing GetDisplayData API.

## Offline compatibility evidence tool

`firmware/inspect_dump.py` reads an existing, legitimately obtained raw
firmware dump **on the PC only**. It computes SHA-256, extracts the expected
version location and compares file ranges with upstream CHDK CRC blocks.
It never opens USB, executes camera code, writes camera memory or modifies
the input. Supply the dump's known base address explicitly:

```console
python firmware/inspect_dump.py PRIMARY.BIN --base-address 0xff810000
python -m unittest firmware.test_inspect_dump
```

The example base applies only if byte zero really maps to that address.
Missing regions stay `missing`, mismatches stay `mismatch`, and no match is
reported unless **both** upstream blocks match. A firmware string alone is
not considered a match. Do not upload proprietary firmware dumps to this
repository. This tool is an analysis aid, not a firmware flasher.

## Feasibility gates, in order

1. **Identity and baseline:** verify exact firmware and official CHDK build;
   preserve the original card contents. Collect CHDK/platform/build info,
   raw GetDisplayData responses in photo/movie standby, source dimensions,
   FPS and USB transfer statistics using stable host tooling.
2. **Recording coexistence:** with stock settings, manually start a short
   recording while PTP polling is active. Record whether USB remains usable,
   whether polling stalls and whether the SD clip is valid. Do not assume
   simultaneous PTP/record mode support because display capture works.
3. **Offline pipeline mapping:** use matching firmware disassembly and CHDK
   generated function maps to follow movie task dispatch and movie writer
   calls. Identify encoded packet types, length fields, codec configuration
   (SPS/PPS), keyframes, presentation order and buffer ownership. A pointer
   or branch target alone is insufficient evidence of a safe hook.
4. **Observe before redirecting:** only after matching firmware analysis,
   design a reversible CHDK diagnostic build with bounded event logging.
   It should report sizes/timing and counters without retaining Canon-owned
   pointers after callbacks. Benchmark overhead while stock SD recording is
   preserved. Never block Canon's encoder or storage task on a USB read.
5. **Bounded copy prototype:** if ownership is established, copy packets to
   a small preallocated ring. Define lengths, sequence numbers, timestamp
   units, codec headers, overflow counters, maximum packet bounds and an
   explicit versioned host handshake. Drop through the next IDR after loss;
   don't publish broken interframe references. No camera hook is supplied
   here because the required ownership evidence is absent.
6. **USB extraction:** add a separate experimental PTP operation or a
   capability-negotiated extension. Do not reuse CWCM as if it were CHDK
   GetDisplayData. Measure sustained transfer plus SD recording, CPU load,
   memory bounds, temperature, recovery after USB loss and long runs.
7. **No-SD recording:** investigate only after successful bounded capture
   with SD recording. Suppressing file writes may change timing, encoder
   flow control and buffer release. The existing source does not prove it
   is possible. Stock recording plus extraction may remain necessary.

For 30 Mbps, encoded payload alone is 3.75 MB/s; transfer overhead and burst
sizes require margin. USB theoretical speed does not settle firmware task
scheduling or sustained PTP performance. MJPEG camera output and arbitrary
bitrates remain unconfirmed. Do not add those as camera capabilities.

## Safety and recovery for later hardware experiments

Keep experimental CHDK builds and manifests separate from normal host
releases. Build against the exact upstream revision/firmware target using
the CHDK toolchain instructions; there is no custom streaming camera build
to compile in this repository yet. Start with a spare SD card and a stock
CHDK build known to boot the exact camera. Preserve a recovery card without
experimental auto-start scripts. Stop on unexplained crashes, file damage,
heat or repeated disconnects. After a failed reversible experiment, power
off, remove battery/USB, restore the known-good SD contents and boot with
the original Canon firmware. Never alter permanent firmware, copy another
revision's addresses or expose unchecked memory read/write controls in the
Windows GUI. Battery/USB interaction and long-duration power need physical
validation with the correct accessories.

## Required decision record

A future native-streaming claim must include exact camera/firmware/CHDK
versions, source commit, ownership analysis, USB traces, original encoded
samples, ffprobe codec/resolution/FPS results, timestamps, sustained bitrate
and recording/USB coexistence results. If the gates fail, record the precise
failure and retain the stable clean-viewport plus host-encoding baseline.
The available source currently proves neither impossibility nor viability
of native full-resolution extraction.
