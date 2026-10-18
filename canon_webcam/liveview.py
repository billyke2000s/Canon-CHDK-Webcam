"""Defensive parser for CHDK live-view protocol 2.x, viewport only."""
from dataclasses import dataclass
import struct

HEADER = struct.Struct('<7i')
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


def parse_viewport(data: bytes) -> Viewport:
    if len(data) < HEADER.size or len(data) > MAX_PAYLOAD:
        raise ValueError('invalid live-view response size')
    major, minor, _aspect, _palette, _pal_start, vp_start, _bm_start = HEADER.unpack_from(data)
    if major != 2:
        raise ValueError(f'unsupported live-view major version: {major}')
    if vp_start < HEADER.size or vp_start + DESC.size > len(data):
        raise ValueError('missing viewport descriptor')
    kind, start, stride, width, height, *_margins = DESC.unpack_from(data, vp_start)
    if kind not in (LV_FB_YUV8, LV_FB_YUV8B, LV_FB_YUV8C):
        raise ValueError(f'unsupported viewport pixel format: {kind}')
    if not (0 < width <= stride <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        raise ValueError('invalid viewport dimensions')
    if width % 2 or stride % 2 or (kind == LV_FB_YUV8 and stride % 4):
        raise ValueError('unsupported chroma alignment')
    bytes_per_row = stride * (3 if kind == LV_FB_YUV8 else 2) // (2 if kind == LV_FB_YUV8 else 1)
    size = bytes_per_row * height
    if start <= 0 or start + size > len(data):
        raise ValueError('viewport pixels missing or truncated')
    return Viewport(width, height, stride, kind, data[start:start + size], (major, minor))


def _rgb(y, u, v):
    c, d, e = max(0, y - 16), u - 128, v - 128
    return (max(0, min(255, (298*c + 409*e + 128) >> 8)),
            max(0, min(255, (298*c - 100*d - 208*e + 128) >> 8)),
            max(0, min(255, (298*c + 516*d + 128) >> 8)))


def to_rgb(view: Viewport) -> bytes:
    """Decode YUV8 (UYVYYY, six bytes/four pixels) or YUV8B/C (UYVY)."""
    out = bytearray(view.width * view.height * 3)
    group_pixels = 4 if view.format == LV_FB_YUV8 else 2
    group_bytes = 6 if view.format == LV_FB_YUV8 else 4
    if view.width % group_pixels:
        raise ValueError('viewport width incompatible with pixel packing')
    src_row = view.buffer_width * group_bytes // group_pixels
    dst = 0
    for row in range(view.height):
        base = row * src_row
        for col in range(0, view.width, group_pixels):
            pos = base + (col // group_pixels) * group_bytes
            group = view.pixels[pos:pos + group_bytes]
            if view.format == LV_FB_YUV8:
                u, y0, v, y1, y2, y3 = group
                ys = (y0, y1, y2, y3)
            else:
                u, y0, v, y1 = group
                ys = (y0, y1)
            for y in ys:
                out[dst:dst+3] = bytes(_rgb(y, u, v))
                dst += 3
    return bytes(out)


def ppm_bytes(view: Viewport) -> bytes:
    return f'P6\n{view.width} {view.height}\n255\n'.encode('ascii') + to_rgb(view)
