import unittest
from unittest.mock import patch
import zlib
from firmware.inspect_dump import inspect_dump, VERSION_ADDRESS


class DumpTests(unittest.TestCase):
    def test_missing_regions_never_match(self):
        result = inspect_dump(b'GM1.01A\0', VERSION_ADDRESS)
        self.assertEqual(result['version_string'], 'GM1.01A')
        self.assertEqual(result['crc_matching_revisions'], [])
        self.assertFalse(result['hardware_verified'])
        self.assertEqual(result['candidates']['GM1.01A'][0]['status'], 'missing')

    def test_synthetic_crc_ranges_require_both_blocks(self):
        # Synthetic signatures exercise matching without shipping Canon firmware.
        data = b'GM.TEST\0' + bytes(range(16)) + b'payload'
        base = 0x1000
        blocks = {'SYNTHETIC': ((base + 8, 16, zlib.crc32(data[8:24])),
                                (base + 24, 7, zlib.crc32(data[24:31])))}
        with patch('firmware.inspect_dump.BLOCKS', blocks), \
             patch('firmware.inspect_dump.VERSION_ADDRESS', base):
            result = inspect_dump(data, base)
            self.assertEqual(result['crc_matching_revisions'], ['SYNTHETIC'])
            self.assertFalse(result['hardware_verified'])
            damaged = data[:-1] + bytes([data[-1] ^ 1])
            self.assertEqual(inspect_dump(damaged, base)['crc_matching_revisions'], [])
            self.assertEqual(inspect_dump(data[:-1], base)['crc_matching_revisions'], [])

    def test_bad_data_does_not_match(self):
        result = inspect_dump(bytes(5_000_000), 0xff810000)
        self.assertEqual(result['crc_matching_revisions'], [])
        self.assertEqual(result['candidates']['GM1.01A'][0]['status'], 'mismatch')


if __name__ == '__main__':
    unittest.main()
