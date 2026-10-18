# CHDK live-view decoder

The CHDK PTP vendor operation is 0x9999. The GetDisplayData
subcommand is 4, with viewport-only transfer flag 0x01. The USB
transport is **not implemented** in this module.

The response begins with seven little-endian signed 32-bit fields.
The viewport descriptor is nine signed 32-bit fields. This decoder
supports protocol major version 2, viewport YUV8 (UYVYYY) and
YUV8B/YUV8C (UYVY). It deliberately ignores bitmap/overlay planes,
yielding a clean viewport.

Example with a saved raw GetDisplayData response:

```python
from canon_webcam.liveview import parse_viewport, ppm_bytes
raw = open('response.bin', 'rb').read()
view = parse_viewport(raw)
open('preview.ppm', 'wb').write(ppm_bytes(view))
```

The viewport may be significantly smaller than 1080p.
Camera-specific descriptor correctness and pixel packing must be
checked with real captures. The conversion is a reference Python
implementation, not yet optimized for continuous high-FPS playback.

Protocol references:
- https://github.com/gphoto/libgphoto2/blob/master/camlibs/ptp2/chdk_live_view.h
- https://android.googlesource.com/platform/external/libmtp/+/f95d04c17d7f9dfe74ae061b97ef594c434f9003/src/chdk_ptp.h
