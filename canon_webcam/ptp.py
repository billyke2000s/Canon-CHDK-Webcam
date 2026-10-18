"""Read-only CHDK PTP operations over a bounded USB bulk byte transport.

This implements standard PTP containers, not the experimental CWCM envelope.
A failed/partial transaction poisons the session: reconnect before retrying.
"""
from dataclasses import dataclass
import logging
import struct
import threading
import time
from typing import Protocol

LOG = logging.getLogger(__name__)
HEADER = struct.Struct('<IHHI')
PTP_OK = 0x2001
CHDK_OPERATION = 0x9999
GET_DISPLAY_DATA = 12
MAX_CONTAINER = 64 * 1024 * 1024


class PTPError(RuntimeError):
    pass


class PTPResponseError(PTPError):
    def __init__(self, code):
        self.code = code
        super().__init__(f'camera returned PTP response 0x{code:04x}')


class ByteTransport(Protocol):
    def read(self, size: int, timeout_ms: int) -> bytes: ...
    def write(self, data: bytes, timeout_ms: int) -> int: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class DeviceInfo:
    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    operations: tuple[int, ...]
    vendor_extension_id: int
    vendor_extension_description: str


def parse_device_info(data: bytes) -> DeviceInfo:
    """Parse the standard PTP DeviceInfo dataset with checked offsets."""
    if len(data) > 1024 * 1024:
        raise PTPError('DeviceInfo dataset exceeds safety limit')
    pos = 0

    def unpack(fmt):
        nonlocal pos
        s = struct.Struct('<' + fmt)
        if pos + s.size > len(data):
            raise PTPError('truncated DeviceInfo dataset')
        result = s.unpack_from(data, pos)
        pos += s.size
        return result[0] if len(result) == 1 else result

    def string():
        nonlocal pos
        count = unpack('B')
        if not count:
            return ''
        size = count * 2
        if pos + size > len(data):
            raise PTPError('truncated PTP string')
        raw = data[pos:pos + size]
        pos += size
        if raw[-2:] != b'\0\0':
            raise PTPError('unterminated PTP string')
        try:
            return raw[:-2].decode('utf-16-le')
        except UnicodeDecodeError as exc:
            raise PTPError('invalid PTP string') from exc

    def array():
        count = unpack('I')
        if count > 65536 or count > (len(data) - pos) // 2:
            raise PTPError('truncated PTP operation array')
        return tuple(unpack('H') for _ in range(count))

    unpack('H')  # standard version
    vendor_id = unpack('I')
    unpack('H')  # vendor extension version
    description = string()
    unpack('H')  # functional mode
    operations = array()
    for _ in range(4):
        array()  # events, properties, capture formats, image formats
    return DeviceInfo(string(), string(), string(), string(), operations,
                      vendor_id, description)


class PTPSession:
    def __init__(self, transport: ByteTransport, timeout_ms=5000,
                 max_container=MAX_CONTAINER):
        if not 1 <= timeout_ms <= 120000 or not 12 <= max_container <= MAX_CONTAINER:
            raise ValueError('invalid PTP timeout or container limit')
        self.transport = transport
        self.timeout_ms = timeout_ms
        self.max_container = max_container
        self._buffer = bytearray()
        self._transaction_id = 0
        self._lock = threading.Lock()
        self.failed = False
        self.bytes_received = 0
        self.bytes_sent = 0

    def _remaining(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('PTP transaction deadline exceeded')
        return max(1, int(remaining * 1000))

    def _container(self, deadline):
        empty_transfers = 0
        while True:
            if len(self._buffer) >= HEADER.size:
                length, kind, code, transaction = HEADER.unpack_from(self._buffer)
                if not HEADER.size <= length <= self.max_container:
                    raise PTPError('invalid PTP container size')
                if kind not in (2, 3):
                    raise PTPError('unexpected PTP container type')
                if len(self._buffer) >= length:
                    payload = bytes(self._buffer[HEADER.size:length])
                    del self._buffer[:length]
                    return kind, code, transaction, payload
            chunk = bytes(self.transport.read(65536, self._remaining(deadline)))
            if not chunk:
                # An exact bulk packet boundary may leave a terminating ZLP.
                # Permit one, retaining the original transaction deadline.
                empty_transfers += 1
                if empty_transfers > 1:
                    raise PTPError('repeated empty USB transfers / disconnected camera')
                continue
            if len(chunk) > 65536:
                raise PTPError('USB transport exceeded requested read size')
            self.bytes_received += len(chunk)
            self._buffer.extend(chunk)

    def transaction(self, operation, params=(), receive_data=False):
        if not 0 <= operation <= 0xffff or len(params) > 5 or any(
                not 0 <= p <= 0xffffffff for p in params):
            raise ValueError('invalid PTP operation or parameters')
        with self._lock:
            if self.failed:
                raise PTPError('PTP session failed; reconnect required')
            transaction = 0 if operation in (0x1001, 0x1002) else self._transaction_id + 1
            if transaction >= 0xffffffff:
                raise PTPError('PTP transaction IDs exhausted; reconnect required')
            if operation not in (0x1001, 0x1002):
                self._transaction_id = transaction
            command = HEADER.pack(12 + 4 * len(params), 1, operation, transaction)
            command += struct.pack('<' + 'I' * len(params), *params)
            deadline = time.monotonic() + self.timeout_ms / 1000
            try:
                offset = 0
                while offset < len(command):
                    count = self.transport.write(command[offset:], self._remaining(deadline))
                    if not isinstance(count, int) or not 0 < count <= len(command) - offset:
                        raise PTPError('invalid USB write result')
                    offset += count
                    self.bytes_sent += count
                kind, code, tid, payload = self._container(deadline)
                data = None
                if tid != transaction:
                    raise PTPError('PTP transaction ID mismatch')
                if kind == 2:
                    if not receive_data or code != operation:
                        raise PTPError('unexpected PTP data phase')
                    data = payload
                    kind, code, tid, payload = self._container(deadline)
                if kind != 3 or tid != transaction or len(payload) % 4 or len(payload) > 20:
                    raise PTPError('invalid PTP response')
                if code != PTP_OK:
                    raise PTPResponseError(code)
                if receive_data and data is None:
                    raise PTPError('missing PTP data phase')
                response = struct.unpack('<' + 'I' * (len(payload) // 4), payload)
                LOG.debug('PTP operation=%04x transaction=%d data=%d', operation,
                          transaction, len(data or b''))
                return data, response
            except PTPResponseError:
                raise
            except Exception:
                self.failed = True
                self._buffer.clear()
                raise


class CHDKCamera:
    """Session lifecycle and verified CHDK viewport command selection.

    No memory reads/writes, script execution or firmware mutations are used.
    Standard DeviceInfo discovers operations; CHDK has no per-subcommand list.
    """
    def __init__(self, transport: ByteTransport, timeout_ms=5000):
        self.session = PTPSession(transport, timeout_ms)
        self.device_info = None
        self.protocol_version = None
        self.connected = False
        self._opened = False

    def connect(self) -> DeviceInfo:
        if self.connected or self._opened:
            raise PTPError('camera session already open')
        try:
            data, _ = self.session.transaction(0x1001, receive_data=True)
            self.device_info = parse_device_info(data)
            if CHDK_OPERATION not in self.device_info.operations:
                raise PTPError('camera does not advertise the CHDK PTP extension')
            self.session.transaction(0x1002, (1,))
            self._opened = True
            _, version = self.session.transaction(CHDK_OPERATION, (0,))
            if len(version) < 2:
                raise PTPError('missing CHDK protocol version')
            self.protocol_version = version[:2]
            if version[0] != 2 or version[1] < 3:
                raise PTPError(f'unsupported CHDK live-view protocol {version[:2]}')
            self.connected = True
            LOG.info('Connected %s firmware=%s CHDK=%s', self.device_info.model,
                     self.device_info.firmware_version, self.protocol_version)
            return self.device_info
        except Exception:
            self.close()
            raise

    def get_live_view(self, flags=1) -> bytes:
        if not self.connected:
            raise PTPError('camera is not connected')
        if flags != 1:
            raise ValueError('only clean viewport requests (flags=1) are supported')
        data, params = self.session.transaction(CHDK_OPERATION,
                                                (GET_DISPLAY_DATA, flags), True)
        if not params or params[0] != len(data):
            self.session.failed = True
            raise PTPError('CHDK live-view response length mismatch')
        return data

    def close(self):
        try:
            if self._opened and not self.session.failed:
                try:
                    self.session.transaction(0x1003)
                except Exception:
                    LOG.debug('PTP close-session failed', exc_info=True)
        finally:
            self._opened = self.connected = False
            self.session.transport.close()
