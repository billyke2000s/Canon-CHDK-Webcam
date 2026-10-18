import unittest
from firmware.inspect_dump import inspect_dump, VERSION_ADDRESS


class DumpTests(unittest.TestCase):
    def test_missing_regions_never_match(self):
        result = inspect_dump(b'GM1.01A\0', VERSION_ADDRESS)
        self.assertEqual(result['version_string'], 'GM1.01A')
        self.assertEqual(result['crc_matching_revisions'], [])
        self.assertFalse(result['hardware_verified'])
        self.assertEqual(result['candidates']['GM1.01A'][0]['status'], 'missing')

    def test_bad_data_does_not_match(self):
        result = inspect_dump(bytes(5_000_000), 0xff810000)
        self.assertEqual(result['crc_matching_revisions'], [])
        self.assertEqual(result['candidates']['GM1.01A'][0]['status'], 'mismatch')


if __name__ == '__main__':
    unittest.main()
