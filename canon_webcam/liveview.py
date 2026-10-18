"""Defensive CHDK live-view 2.x viewport parsing and full-range YUV decoding.

The protocol is independent of CWCM. Bitmap planes are deliberately omitted.
See docs/chdk-liveview.md for upstream format and display-aspect references.
"""
from dataclasses import dataclass
import struct

HEADER = struct.Struct('<7i')  # common 2.0 prefix; 2.2 adds bmo_desc_start
DESC = struct.Struct('<9i')
LV_FB_YUV8 = 0
LV_FB_YUV8B = 2
LV_FB_YUV8C = 3
MAX_DIMENSION = 8192
MAX_PAYLOAD = 64 * 1024 * 1024


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    buffer_width: int
    format: int
    pixels: bytes
    version: tuple[int, int]
    margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    lcd_aspect: int = 0

    @property
    def display_aspect(self) -> float:
        """Active image aspect after correcting non-square framebuffer pixels."""
        aspect = {0: 4 / 3, 1: 16 / 9, 2: 3 / 2}.get(self.lcd_aspect)
        if aspect is None:  # future protocol enum: preserve pixels, don't guess
            return self.width / self.height
        left, top, right, bottom = self.margins
        return aspect * self.width / (self.width + left + right) * (
            self.height + top + bottom) / self.height


def parse_viewport(data: bytes) -> Viewport:
    if len(data) < HEADER.size or len(data) > MAX_PAYLOAD:
        raise ValueError('invalid live-view response size')
    major, minor, aspect, _palette, _pal_start, vp_start, _bm_start = HEADER.unpack_from(data)
    if major != 2 or minor < 0:
        raise ValueError(f'unsupported live-view version: {major}.{minor}')
    header_size = 32 if minor >= 2 else HEADER.size
    if vp_start < header_size or vp_start + DESC.size > len(data):
        raise ValueError('missing viewport descriptor')
    kind, start, stride, width, height, *margins = DESC.unpack_from(data, vp_start)
    if kind not in (LV_FB_YUV8, LV_FB_YUV8B, LV_FB_YUV8C):
        raise ValueError(f'unsupported viewport pixel format: {kind}')
    if not (0 < width <= stride <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        raise ValueError('invalid viewport dimensions')
    group = 4 if kind == LV_FB_YUV8 else 2
    if stride % group:
        raise ValueError('unsupported chroma alignment')
    if any(m < 0 or m > MAX_DIMENSION for m in margins):
        raise ValueError('invalid display margins')
    if width + margins[0] + margins[2] > MAX_DIMENSION or height + margins[1] + margins[3] > MAX_DIMENSION:
        raise ValueError('display dimensions too large')
    bytes_per_row = stride * (3 if kind == LV_FB_YUV8 else 4) // 2
    size = bytes_per_row * height
    if start < vp_start + DESC.size or start + size > len(data):
        raise ValueError('viewport pixels missing, overlapping, or truncated')
    return Viewport(width, height, stride, kind, bytes(data[start:start + size]),
                    (major, minor), tuple(margins), aspect)


def _rgb(y, u, v):
    return tuple(max(0, min(255, c)) for c in (
        ((y << 12) + v * 5743 + 2048) >> 12,
        ((y << 12) - u * 1411 - v * 2925 + 2048) >> 12,
        ((y << 12) + u * 7258 + 2048) >> 12))


def _signed(chroma: int) -> int:
    return chroma - 256 if chroma >= 128 else chroma


def to_rgb_reference(view: Viewport) -> bytes:
    """Slow, dependency-free oracle; production uses the NumPy path."""
    out = bytearray()
    group_pixels = 4 if view.format == LV_FB_YUV8 else 2
    group_bytes = 6 if view.format == LV_FB_YUV8 else 4
    src_row = view.buffer_width * group_bytes // group_pixels
    for row in range(view.height):
        for col in range(0, view.width, group_pixels):
            pos = row * src_row + col // group_pixels * group_bytes
            group = view.pixels[pos:pos + group_bytes]
            if len(group) != group_bytes:
                raise ValueError('truncated viewport')
            u, _, v, *_ = group
            u, v = ((u - 128, v - 128) if view.format == LV_FB_YUV8B else (_signed(u), _signed(v)))
            ys = (group[1], group[3], group[4], group[5]) if group_pixels == 4 else (group[1], group[3])
            for y in ys[:min(group_pixels, view.width - col)]:
                out.extend(_rgb(y, u, v))
    return bytes(out)


def rgb_array(view: Viewport):
    """Return full-range RGB uint8 HWC without per-pixel Python loops."""
    import numpy as np
    group_pixels = 4 if view.format == LV_FB_YUV8 else 2
    group_bytes = 6 if view.format == LV_FB_YUV8 else 4
    packed = np.frombuffer(view.pixels, dtype=np.uint8).reshape(
        view.height, view.buffer_width // group_pixels, group_bytes)
    y_indices = [1, 3, 4, 5] if group_pixels == 4 else [1, 3]
    y = packed[:, :, y_indices].reshape(view.height, view.buffer_width)[:, :view.width].astype(np.int32)
    chroma = packed[:, :, [0, 2]].astype(np.int32)
    if view.format == LV_FB_YUV8B:
        chroma -= 128
    else:
        chroma[chroma >= 128] -= 256
    uv = np.repeat(chroma, group_pixels, axis=1)[:, :view.width]
    u, v = uv[:, :, 0], uv[:, :, 1]
    base = (y << 12) + 2048
    rgb = np.stack(((base + v * 5743) >> 12,
                    (base - u * 1411 - v * 2925) >> 12,
                    (base + u * 7258) >> 12), axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def to_rgb(view: Viewport) -> bytes:
    """Decode the active image; row padding and display margins aren't pixels."""
    try:
        return rgb_array(view).tobytes()
    except ImportError:
        return to_rgb_reference(view)


def normalize_rgb(view: Viewport, rotation: int = 0):
    """Square-pixel active viewport, excluding margins, explicitly rotated.

    The protocol has no orientation or timestamp field. Keep receipt timestamps
    in capture metadata and supply orientation from a user setting if required.
    Resizing is display geometry correction; it does not increase source detail.
    """
    import numpy as np
    if rotation not in (0, 90, 180, 270):
        raise ValueError('rotation must be 0, 90, 180, or 270')
    pixels = rgb_array(view)
    width = max(1, round(view.height * view.display_aspect))
    # Keep dimensions bounded even when constructing Viewport directly.
    if width > MAX_DIMENSION:
        raise ValueError('normalized width too large')
    if width != view.width:
        # Geometry-only nearest sampling avoids pulling in another image library.
        indices = np.minimum(np.arange(width) * view.width // width, view.width - 1)
        pixels = pixels[:, indices]
    if rotation:
        pixels = np.rot90(pixels, -(rotation // 90))
    return np.ascontiguousarray(pixels)


def ppm_bytes(view: Viewport) -> bytes:
    return f'P6\n{view.width} {view.height}\n255\n'.encode('ascii') + to_rgb(view)
