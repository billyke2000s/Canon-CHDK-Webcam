# USB/PTP adapter

## Status

`canon_webcam.usb` uses PyUSB/libusb bulk endpoints. `canon_webcam.ptp`
implements checked standard PTP containers, DeviceInfo discovery, session
ownership, CHDK version negotiation and viewport requests. These paths have
synthetic USB tests, **not physical-camera verification**. The adapter does not
extract native H.264, set camera properties, execute scripts or access camera
memory. USB visibility alone does not prove CHDK compatibility.

The adapter discovers Canon USB devices (vendor `04a9`), selects the still-image
interface (class 6, alternate setting 0), and requires both bulk IN and bulk OUT.
One device is selected automatically; multiple devices require explicit selection.
When a readable serial descriptor exists, reconnect follows that serial across
USB bus/address changes. Without one, selection remains tied to its current USB
address: explicit reselection may be necessary after unplugging. It never silently
substitutes a different serial-numbered camera.

## Windows setup

Install the application's USB dependency extra (`pip install .[usb]` for source
installs). PyUSB needs a native libusb backend; the optional `libusb-package`
dependency supplies a backend DLL and its packaging hook. The adapter explicitly
resolves that package's backend when available and otherwise uses PyUSB discovery.
The Windows PTP/WPD driver can prevent libusb from opening the camera. Close Canon
utilities and other PTP applications first. If a compatible WinUSB/libusb driver
is needed, choose only the camera's PTP interface in a trusted driver setup tool,
record its original driver, and retain the ability to restore it in Device Manager.
A driver change can temporarily prevent ordinary Windows photo transfer.

There is no automatic driver replacement, kernel-driver detachment or firmware
installation. Access errors surface to the application with the original exception.
Do not run two CHDK/PTP clients concurrently.

## Wire behavior

Standard little-endian PTP container header: `length:uint32`, `type:uint16`,
`code:uint16`, `transaction:uint32`. Commands carry at most five uint32
parameters. Incoming data is limited to 64 MiB per container. Bulk reads are
64 KiB or less, allowing normal endpoint packet sizes and partial/coalesced
transfers without assuming one read equals one container. One monotonic deadline
covers each entire transaction, so partial transfers do not extend it forever.

1. GetDeviceInfo (`1001`, transaction 0), checked dataset parsing and supported
   operation discovery. Firmware version is Canon's reported DeviceVersion;
   it may not identify the exact CHDK firmware revision.
2. Require vendor operation `9999`, then OpenSession (`1002`, transaction 0).
   A pre-existing session is rejected rather than closed without ownership.
3. CHDK Version (`9999`, parameter 1 = 0). Require major 2, minor at least 3.
4. GetDisplayData (`9999`, parameter 1 = **12**, parameter 2 = **1** for
   viewport only). Read the data phase and validate its size against response
   parameter 1. Bitmap/palette overlays are not requested. This cannot remove
   graphics already baked into a camera's selected viewport.
5. CloseSession (`1003`) only if this adapter opened it and transport state is
   still synchronized; release interface and dispose libusb resources regardless.

CHDK does not provide a general per-subcommand enumeration operation. Standard
DeviceInfo advertises the CHDK vendor operation; protocol version establishes
the documented live-view baseline. Actual framebuffer capability comes from the
returned live-view descriptor and must be checked by the decoder. Unsupported
camera modes may still reject the request.

Transaction IDs, container type, data operation code and response parameter
length are checked. A timeout, disconnect, malformed packet or partial failed
transaction invalidates the session. Recovery must dispose it and establish a
fresh session, avoiding reuse of a potentially desynchronized stream. A complete
camera error response leaves framing synchronized and surfaces `PTPResponseError`.
No failed command is blindly replayed inside a transaction.

Session byte counters measure actual transferred container bytes. A caller can
sample the counters against monotonic elapsed time for observed throughput;
these counters are not a claim about maximum sustained camera bandwidth.

## Primary protocol references

Verified against the CHDK source enum and comments in
[`trunk/core/ptp.h`](https://github.com/petabyt/chdk/blob/master/trunk/core/ptp.h)
and the camera-side handler in
[`trunk/core/ptp.c`](https://github.com/petabyt/chdk/blob/master/trunk/core/ptp.c).
The enum places GetDisplayData at 12. Subcommand 4 is TempData and must **not**
be used for live view. Protocol history records released live view in 2.3.
The separate display payload specification is
[`trunk/core/live_view.h`](https://github.com/petabyt/chdk/blob/master/trunk/core/live_view.h).
PyUSB's maintained implementation and backend documentation are available at
[pyusb/pyusb](https://github.com/pyusb/pyusb).

## Verification

Run `python -m unittest tests.test_ptp tests.test_usb -v`. Tests cover bounded
parsing, DeviceInfo truncation at every boundary, partial reads/writes, coalesced
data/response containers, command numbering, session lifecycle, transaction
mismatches, invalid response sizes, timeout poisoning, missing CHDK support,
reconnect with a fresh transport, serial-based selection and resource cleanup.
These tests use synthetic responses. Hardware must establish driver behavior,
USB speed, camera mode transitions, sustained frame cadence and clean viewport
availability before claiming physical compatibility.
