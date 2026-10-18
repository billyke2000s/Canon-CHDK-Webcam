import struct
import unittest
from collections import deque

from canon_webcam.ptp import (CHDKCamera, CHDK_OPERATION, GET_DISPLAY_DATA,
                              HEADER, PTPError, PTPResponseError, PTPSession,
                              parse_device_info)


def container(kind, code, tid, payload=b''):
    return HEADER.pack(12 + len(payload), kind, code, tid) + payload


def response(tid, *params, code=0x2001):
    return container(3, code, tid, struct.pack('<' + 'I' * len(params), *params))


def ptp_string(value):
    return bytes([len(value) + 1]) + value.encode('utf-16-le') + b'\0\0'


def device_info(operations=(0x1001, 0x1002, 0x1003, CHDK_OPERATION)):
    return (struct.pack('<HIH', 100, 0, 100) + ptp_string('CHDK') +
            struct.pack('<HI', 0, len(operations)) +
            struct.pack('<' + 'H' * len(operations), *operations) + b'\0' * 16 +
            b''.join(ptp_string(v) for v in ('Canon', 'IXUS 117 HS', '1.00c', 'synthetic')))


class FakeTransport:
    def __init__(self, reads=(), partial_write=None):
        self.reads = deque(reads)
        self.writes = bytearray()
        self.closed = False
        self.partial_write = partial_write

    def read(self, size, timeout_ms):
        assert size <= 65536 and timeout_ms > 0
        item = self.reads.popleft()
        if isinstance(item, Exception):
            raise item
        if len(item) > size:
            self.reads.appendleft(item[size:])
            item = item[:size]
        return item

    def write(self, data, timeout_ms):
        count = min(self.partial_write or len(data), len(data))
        self.writes.extend(data[:count])
        return count

    def close(self):
        self.closed = True


class PTPTests(unittest.TestCase):
    def test_device_info(self):
        info = parse_device_info(device_info())
        self.assertEqual(info.model, 'IXUS 117 HS')
        self.assertEqual(info.firmware_version, '1.00c')
        self.assertIn(CHDK_OPERATION, info.operations)

    def test_truncated_info_every_boundary(self):
        data = device_info()
        for end in range(len(data)):
            with self.subTest(end=end), self.assertRaises(PTPError):
                parse_device_info(data[:end])

    def test_partial_transfers_and_coalesced_containers(self):
        data = container(2, 0x1001, 0, device_info()) + response(0)
        transport = FakeTransport([data[:3], data[3:11], data[11:]], partial_write=2)
        session = PTPSession(transport)
        payload, params = session.transaction(0x1001, receive_data=True)
        self.assertEqual(payload, device_info())
        self.assertEqual(params, ())
        self.assertEqual(bytes(transport.writes), container(1, 0x1001, 0))
        self.assertEqual(session.bytes_received, len(data))
        self.assertEqual(session.bytes_sent, 12)

    def test_connect_liveview_close(self):
        transport = FakeTransport([
            container(2, 0x1001, 0, device_info()) + response(0),
            response(0), response(1, 2, 9),
            container(2, CHDK_OPERATION, 2, b'frame') + response(2, 5),
            response(3),
        ])
        camera = CHDKCamera(transport)
        self.assertEqual(camera.connect().manufacturer, 'Canon')
        self.assertEqual(camera.protocol_version, (2, 9))
        self.assertEqual(camera.get_live_view(), b'frame')
        camera.close()
        self.assertTrue(transport.closed)
        self.assertFalse(camera.connected)
        commands = bytes(transport.writes)
        self.assertIn(container(1, CHDK_OPERATION, 2, struct.pack('<II', 12, 1)), commands)
        self.assertEqual(GET_DISPLAY_DATA, 12)

    def test_missing_chdk_closes_without_open(self):
        transport = FakeTransport([container(2, 0x1001, 0, device_info((0x1001,))) + response(0)])
        with self.assertRaisesRegex(PTPError, 'does not advertise'):
            CHDKCamera(transport).connect()
        self.assertTrue(transport.closed)
        self.assertEqual(len(transport.writes), 12)

    def test_unsupported_protocol_closes_owned_session(self):
        transport = FakeTransport([container(2, 0x1001, 0, device_info()) + response(0),
                                   response(0), response(1, 2, 1), response(2)])
        with self.assertRaisesRegex(PTPError, 'unsupported'):
            CHDKCamera(transport).connect()
        self.assertTrue(transport.closed)
        self.assertTrue(bytes(transport.writes).endswith(container(1, 0x1003, 2)))

    def test_timeout_poisoned_session_requires_new_connection(self):
        transport = FakeTransport([TimeoutError('synthetic timeout')])
        session = PTPSession(transport)
        with self.assertRaises(TimeoutError):
            session.transaction(0x1001, receive_data=True)
        with self.assertRaisesRegex(PTPError, 'reconnect'):
            session.transaction(0x1001, receive_data=True)

    def test_zero_progress_disconnect(self):
        session = PTPSession(FakeTransport([b'', b'']))
        with self.assertRaisesRegex(PTPError, 'empty USB'):
            session.transaction(0x1001, receive_data=True)
        self.assertTrue(session.failed)

    def test_oversized_container_rejected_before_payload(self):
        session = PTPSession(FakeTransport([HEADER.pack(0xffffffff, 2, 0x1001, 0)]))
        with self.assertRaisesRegex(PTPError, 'container size'):
            session.transaction(0x1001, receive_data=True)

    def test_transaction_mismatch(self):
        session = PTPSession(FakeTransport([response(999)]))
        with self.assertRaisesRegex(PTPError, 'ID mismatch'):
            session.transaction(0x1001)

    def test_data_operation_mismatch(self):
        session = PTPSession(FakeTransport([container(2, 0x1002, 0, b'x')]))
        with self.assertRaisesRegex(PTPError, 'data phase'):
            session.transaction(0x1001, receive_data=True)

    def test_response_error_consumed_session_remains_usable(self):
        session = PTPSession(FakeTransport([response(0, code=0x2005), response(1)]))
        with self.assertRaises(PTPResponseError):
            session.transaction(0x1001)
        self.assertFalse(session.failed)
        self.assertEqual(session.transaction(0x1003), (None, ()))

    def test_missing_data_phase(self):
        session = PTPSession(FakeTransport([response(0)]))
        with self.assertRaisesRegex(PTPError, 'missing'):
            session.transaction(0x1001, receive_data=True)

    def test_reconnect_uses_new_transport(self):
        failed = FakeTransport([ConnectionError('unplugged')])
        camera = CHDKCamera(failed)
        with self.assertRaises(ConnectionError):
            camera.connect()
        self.assertTrue(failed.closed)
        fresh = FakeTransport([container(2, 0x1001, 0, device_info()) + response(0),
                               response(0), response(1, 2, 9), response(2)])
        replacement = CHDKCamera(fresh)
        replacement.connect()
        self.assertTrue(replacement.connected)
        replacement.close()

    def test_liveview_size_mismatch_poisoned(self):
        transport = FakeTransport([container(2, CHDK_OPERATION, 1, b'x') + response(1, 200)])
        camera = CHDKCamera(transport)
        camera.connected = True
        with self.assertRaisesRegex(PTPError, 'length mismatch'):
            camera.get_live_view()
        self.assertTrue(camera.session.failed)

    def test_invalid_response_parameter_length(self):
        session = PTPSession(FakeTransport([container(3, 0x2001, 0, b'x')]))
        with self.assertRaisesRegex(PTPError, 'invalid PTP response'):
            session.transaction(0x1001)

    def test_timeout_parameters_checked(self):
        for value in (0, -1, 120001):
            with self.assertRaises(ValueError):
                PTPSession(FakeTransport(), timeout_ms=value)

    def test_bulk_zero_length_terminator_before_response(self):
        session = PTPSession(FakeTransport([b'', response(0)]))
        self.assertEqual(session.transaction(0x1001), (None, ()))

    def test_device_info_dataset_bound(self):
        with self.assertRaisesRegex(PTPError, 'safety limit'):
            parse_device_info(b'\0' * (1024 * 1024 + 1))
