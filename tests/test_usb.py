import unittest
from unittest.mock import Mock, patch

from canon_webcam.usb import DeviceIdentity, PyUSBTransport, discover_cameras


class USBTests(unittest.TestCase):
    def test_discovery_does_not_claim(self):
        device = Mock(idVendor=0x04a9, idProduct=0x1234, bus=1, address=2, iSerialNumber=0)
        core, util = Mock(), Mock()
        core.find.return_value = [device]
        with patch('canon_webcam.usb._modules', return_value=(core, util)):
            self.assertEqual(discover_cameras(), [DeviceIdentity(0x04a9, 0x1234, 1, 2)])
        util.claim_interface.assert_not_called()

    def test_bulk_timeout_and_close(self):
        incoming, outgoing, util = Mock(), Mock(), Mock()
        incoming.read.return_value = [1, 2, 3]
        outgoing.write.return_value = 3
        transport = PyUSBTransport('dev', 0, incoming, outgoing, util)
        self.assertEqual(transport.read(65536, 123), b'\1\2\3')
        incoming.read.assert_called_once_with(65536, timeout=123)
        self.assertEqual(transport.write(b'123', 100), 3)
        transport.close()
        transport.close()
        util.release_interface.assert_called_once_with('dev', 0)
        util.dispose_resources.assert_called_once_with('dev')
        with self.assertRaises(ConnectionError):
            transport.read(1, 1)

    def test_ambiguous_devices_refused(self):
        with patch('canon_webcam.usb._modules', return_value=(Mock(), Mock())), patch(
                'canon_webcam.usb.discover_cameras', return_value=[1, 2]):
            with self.assertRaisesRegex(RuntimeError, 'found 2'):
                PyUSBTransport.open()

    def test_disappeared_device(self):
        core = Mock()
        core.find.return_value = None
        with patch('canon_webcam.usb._modules', return_value=(core, Mock())):
            with self.assertRaises(ConnectionError):
                PyUSBTransport.open(DeviceIdentity(0x04a9, 1, 1, 2))

    def test_serial_reconnect_ignores_changed_bus_address(self):
        old = DeviceIdentity(0x04a9, 1, 1, 2, 'camera-123')
        device = Mock(idVendor=0x04a9, idProduct=1, bus=4, address=99, iSerialNumber=1)
        device.get_active_configuration.return_value = []
        core, util = Mock(), Mock()
        core.find.return_value = [device]
        util.get_string.return_value = 'camera-123'
        with patch('canon_webcam.usb._modules', return_value=(core, util)):
            with self.assertRaisesRegex(RuntimeError, 'no supported PTP'):
                PyUSBTransport.open(old)
        device.get_active_configuration.assert_called_once()
        self.assertNotIn('address', core.find.call_args.kwargs)
        util.dispose_resources.assert_called_once_with(device)

    def test_different_serial_never_selected(self):
        device = Mock(iSerialNumber=1)
        core, util = Mock(), Mock()
        core.find.return_value = [device]
        util.get_string.return_value = 'wrong-camera'
        with patch('canon_webcam.usb._modules', return_value=(core, util)):
            with self.assertRaises(ConnectionError):
                PyUSBTransport.open(DeviceIdentity(0x04a9, 1, 1, 2, 'chosen-camera'))
        util.claim_interface.assert_not_called()

    def test_open_selects_ptp_bulk_and_releases(self):
        incoming = Mock(bmAttributes=2, bEndpointAddress=0x81)
        outgoing = Mock(bmAttributes=2, bEndpointAddress=0x02)

        class Interface(list):
            bInterfaceClass = 6
            bAlternateSetting = 0
            bInterfaceNumber = 3

        device = Mock()
        device.get_active_configuration.return_value = [Interface([incoming, outgoing])]
        core, util = Mock(), Mock()
        core.find.return_value = device
        core.USBError = RuntimeError
        util.ENDPOINT_TYPE_BULK = 2
        util.ENDPOINT_IN = 0x80
        util.ENDPOINT_OUT = 0
        util.endpoint_type.side_effect = lambda attributes: attributes & 3
        util.endpoint_direction.side_effect = lambda address: address & 0x80
        with patch('canon_webcam.usb._modules', return_value=(core, util)):
            transport = PyUSBTransport.open(DeviceIdentity(0x04a9, 1, 1, 2))
        self.assertIs(transport.endpoint_in, incoming)
        self.assertIs(transport.endpoint_out, outgoing)
        util.claim_interface.assert_called_once_with(device, 3)
        device.set_configuration.assert_not_called()
        transport.close()
        util.release_interface.assert_called_once_with(device, 3)
        util.dispose_resources.assert_called_once_with(device)

    def test_backend_claim_failure_disposes_resources(self):
        class Interface(list):
            bInterfaceClass = 6
            bAlternateSetting = 0
            bInterfaceNumber = 0

        device = Mock()
        device.get_active_configuration.return_value = [Interface([
            Mock(bmAttributes=2, bEndpointAddress=0x81),
            Mock(bmAttributes=2, bEndpointAddress=0x02)])]
        core, util = Mock(), Mock()
        core.find.return_value = device
        core.USBError = RuntimeError
        util.ENDPOINT_TYPE_BULK = 2
        util.ENDPOINT_IN = 0x80
        util.ENDPOINT_OUT = 0
        util.endpoint_type.side_effect = lambda attributes: attributes & 3
        util.endpoint_direction.side_effect = lambda address: address & 0x80
        util.claim_interface.side_effect = PermissionError('driver owns device')
        with patch('canon_webcam.usb._modules', return_value=(core, util)):
            with self.assertRaises(PermissionError):
                PyUSBTransport.open(DeviceIdentity(0x04a9, 1, 1, 2))
        util.dispose_resources.assert_called_once_with(device)
        util.release_interface.assert_not_called()
