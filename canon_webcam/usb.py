"""Optional PyUSB/libusb adapter. Imports USB dependencies only on use."""
from dataclasses import dataclass
import logging

LOG = logging.getLogger(__name__)
CANON_VENDOR_ID = 0x04a9


@dataclass(frozen=True)
class DeviceIdentity:
    vendor_id: int
    product_id: int
    bus: int | None
    address: int | None
    serial_number: str | None = None


def _modules():
    try:
        import usb.core
        import usb.util
    except ImportError as exc:
        raise RuntimeError('USB capture requires PyUSB and a libusb backend; install the usb extra') from exc
    return usb.core, usb.util


def _backend():
    # libusb-package provides a redistributable DLL and its PyInstaller hook.
    try:
        import libusb_package
        import usb.backend.libusb1
    except ImportError:
        return None
    return usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)


def _serial(device, util):
    try:
        return util.get_string(device, device.iSerialNumber) if device.iSerialNumber else None
    except Exception:
        # Discovery must still list devices whose string descriptors need a driver.
        return None


def discover_cameras() -> list[DeviceIdentity]:
    core, util = _modules()
    try:
        return [DeviceIdentity(d.idVendor, d.idProduct, d.bus, d.address, _serial(d, util))
                for d in core.find(find_all=True, idVendor=CANON_VENDOR_ID, backend=_backend())]
    except core.NoBackendError as exc:
        raise RuntimeError('No libusb backend found; see docs/ptp.md for Windows setup') from exc


class PyUSBTransport:
    def __init__(self, device, interface, endpoint_in, endpoint_out, util):
        self.device = device
        self.interface = interface
        self.endpoint_in = endpoint_in
        self.endpoint_out = endpoint_out
        self._util = util
        self._closed = False

    @classmethod
    def open(cls, identity: DeviceIdentity | None = None):
        core, util = _modules()
        if identity is None:
            devices = discover_cameras()
            if len(devices) != 1:
                raise RuntimeError(f'Expected one Canon USB device, found {len(devices)}; select a device explicitly')
            identity = devices[0]
        if identity.serial_number:
            candidates = core.find(find_all=True, idVendor=identity.vendor_id,
                                   idProduct=identity.product_id, backend=_backend())
            matches = [d for d in candidates if _serial(d, util) == identity.serial_number]
            if len(matches) > 1:
                raise RuntimeError('Multiple devices report the selected serial number')
            device = matches[0] if matches else None
        else:
            device = core.find(idVendor=identity.vendor_id, idProduct=identity.product_id,
                               bus=identity.bus, address=identity.address, backend=_backend())
        if device is None:
            raise ConnectionError('Selected camera is no longer connected')
        claimed = None
        try:
            try:
                config = device.get_active_configuration()
            except core.USBError:
                device.set_configuration()
                config = device.get_active_configuration()
            for interface in config:
                if interface.bInterfaceClass != 6 or interface.bAlternateSetting != 0:
                    continue
                endpoints = [e for e in interface if util.endpoint_type(e.bmAttributes) == util.ENDPOINT_TYPE_BULK]
                incoming = next((e for e in endpoints if util.endpoint_direction(e.bEndpointAddress) == util.ENDPOINT_IN), None)
                outgoing = next((e for e in endpoints if util.endpoint_direction(e.bEndpointAddress) == util.ENDPOINT_OUT), None)
                if incoming is not None and outgoing is not None:
                    util.claim_interface(device, interface.bInterfaceNumber)
                    claimed = interface.bInterfaceNumber
                    LOG.info('Claimed Canon USB %04x:%04x interface=%d',
                             identity.vendor_id, identity.product_id, claimed)
                    return cls(device, claimed, incoming, outgoing, util)
            raise RuntimeError('Selected device has no supported PTP bulk interface')
        except Exception:
            if claimed is not None:
                util.release_interface(device, claimed)
            util.dispose_resources(device)
            raise

    def read(self, size, timeout_ms):
        if self._closed:
            raise ConnectionError('USB transport is closed')
        return bytes(self.endpoint_in.read(size, timeout=timeout_ms))

    def write(self, data, timeout_ms):
        if self._closed:
            raise ConnectionError('USB transport is closed')
        return self.endpoint_out.write(data, timeout=timeout_ms)

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._util.release_interface(self.device, self.interface)
            finally:
                self._util.dispose_resources(self.device)
