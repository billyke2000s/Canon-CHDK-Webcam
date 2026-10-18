# CHDK live-view decoder

`canon_webcam.liveview` parses the CHDK live-view 2.x subprotocol returned
by PTP operation `0x9999`, **GetDisplayData subcommand 12**, viewport flag
`0x01`. This is unrelated to the project's experimental CWCM envelope.
Command 4 is TempData, not GetDisplayData; the earlier documentation
was incorrect.

## Wire and colour correctness

The 2.0 header prefix is seven little-endian signed 32-bit integers.
Version 2.2 adds an eighth `bmo_desc_start` integer. Descriptors are nine
integers. Descriptor and pixel offsets are checked against packet bounds;
zero/unavailable viewport data raises an actionable error instead of being
interpreted as an image. Negative dimensions/margins, unsupported types,
packing misalignment, overlapping pixels and truncation are rejected.

| Type | Numeric value | Packing | U/V interpretation |
|---|---:|---|---|
| YUV8 | 0 | U Y0 V Y1 Y2 Y3, four pixels | signed 8-bit, zero neutral |
| PAL8 | 1 | bitmap plane, unsupported here | palette |
| YUV8B | 2 | U Y0 V Y1, two pixels | unsigned offset 128 |
| YUV8C | 3 | U Y0 V Y1, two pixels | signed 8-bit, zero neutral |

Luma uses the full 0–255 range. Conversion follows the CHDKPTP `liveimg.c`
integer coefficients, rather than limited-range broadcast YUV conversion.
`rgb_array(view)` uses vectorized NumPy operations; `to_rgb_reference(view)`
is a dependency-free test oracle. `to_rgb(view)` prefers NumPy and returns
packed RGB bytes. The latter retains a slow fallback for saved-file tooling;
install desktop/media dependencies for continuous capture.

`buffer_width` determines row stride. Only `visible_width` pixels are
returned, including a partial final chroma group when present. Margins
position the already-cropped image on the LCD: **they are not additional
byte offsets into the payload**. Bitmap, palette and opacity planes are
ignored, avoiding separately composited Canon menus/icons. This cannot
remove marks already burned into a viewport by a camera mode.

## Display geometry and metadata

`view.width` and `view.height` always report actual source sample counts.
`normalize_rgb(view, rotation=0)` returns a contiguous NumPy RGB HWC array,
correcting non-square pixels using the LCD aspect enum and descriptor
margins. It excludes surrounding display margins. Resizing changes display
geometry only; it never creates native-resolution detail. Unknown future
LCD aspect values retain source geometry. Rotation is explicitly 0, 90,
180 or 270 degrees clockwise; CHDK live-view does not transmit orientation.
It also has no camera timestamp: capture code must attach a monotonic host
receipt timestamp and must not advertise camera-clock synchronization.

## Example

```python
from canon_webcam.liveview import parse_viewport, normalize_rgb
view = parse_viewport(open('response.bin', 'rb').read())
rgb = normalize_rgb(view)
print('source', view.width, view.height, 'display', rgb.shape)
```

No descriptor fixture is a hardware recording. Actual IXUS 117 HS viewport
layouts across record/movie modes require saved camera responses. Synthetic
coverage includes colour range, both chroma conventions, NumPy/reference
agreement, row padding, partial groups, display geometry, rotation, old/new
headers and malformed descriptors.

## Primary implementation references

- [libgphoto2 CHDK live-view header](https://github.com/gphoto/libgphoto2/blob/master/camlibs/ptp2/chdk_live_view.h)
- [CHDKPTP colour conversion](https://github.com/svn2github/chdkptp/blob/master/liveimg.c), especially `yuv_to_r/g/b` and `yuv*_live_to_cd_rgb`.
- [CHDK core live-view implementation](https://github.com/petabyt/chdk/blob/ad402e1b2049662594ccc7d15a9a507138b59079/trunk/core/live_view.c)
- [CHDK PTP command enumeration](https://github.com/petabyt/chdk/blob/ad402e1b2049662594ccc7d15a9a507138b59079/trunk/core/ptp.h)
