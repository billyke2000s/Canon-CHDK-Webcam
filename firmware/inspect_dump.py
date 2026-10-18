"""Read-only offline CHDK CRC evidence; never connects to a camera or patches ROM."""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

# Source: CHDK mirror ad402e1b2049662594ccc7d15a9a507138b59079
# trunk/platform/ixus115_elph100hs/sub/{100c,101a,101b}/firmware_crc_data.h
BLOCKS = {
    'GM1.00C': ((0xff810000, 0x387de2, 0xcd30490f), (0xffc7edb8, 0xe9c0, 0x869579df)),
    'GM1.01A': ((0xff810000, 0x387e02, 0x1455fa13), (0xffc7edd8, 0xe9c0, 0x33c52f44)),
    'GM1.01B': ((0xff810000, 0x387e0a, 0x530e736f), (0xffc7ede0, 0xe9c0, 0xeff03ebe)),
    'GM1.01C': ((0xff810000, 0x387e0a, 0xad85af19), (0xffc7ede0, 0xe9c0, 0xeff03ebe)),
}
VERSION_ADDRESS = 0xff8938ad


def inspect_dump(data: bytes, base_address: int) -> dict:
    """Offsets are only file offsets relative to the explicit dump base."""
    version_offset = VERSION_ADDRESS - base_address
    version = ''
    if 0 <= version_offset < len(data):
        version = data[version_offset:version_offset + 16].split(b'\0')[0].decode('ascii', errors='replace')
    candidates = {}
    for name, blocks in BLOCKS.items():
        results = []
        for address, length, expected in blocks:
            offset = address - base_address
            present = 0 <= offset and offset + length <= len(data)
            actual = zlib.crc32(data[offset:offset + length]) if present else None
            results.append({'address': hex(address), 'length': length,
                            'expected_crc32': f'{expected:08x}',
                            'actual_crc32': f'{actual:08x}' if actual is not None else None,
                            'status': 'missing' if not present else ('match' if actual == expected else 'mismatch')})
        candidates[name] = results
    matched = [name for name, blocks in candidates.items()
               if all(block['status'] == 'match' for block in blocks)]
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
            'base_address': hex(base_address), 'version_string': version,
            'crc_matching_revisions': matched, 'candidates': candidates,
            'hardware_verified': False,
            'notice': 'Offline source matching only; not permission to patch or proof of streaming support.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dump', type=Path)
    parser.add_argument('--base-address', type=lambda s: int(s, 0), required=True,
                        help='address corresponding to byte zero, from dump provenance')
    args = parser.parse_args()
    if args.dump.stat().st_size > 64 * 1024 * 1024:
        parser.error('dump larger than 64 MiB; confirm input format')
    print(json.dumps(inspect_dump(args.dump.read_bytes(), args.base_address), indent=2))


if __name__ == '__main__':
    main()
