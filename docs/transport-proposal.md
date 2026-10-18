# Proposed experimental compressed-frame transport

**Not a CHDK protocol extension yet.** This is a testable host-side envelope
for frames that a future firmware experiment might expose.

Binary header: `CWCM` magic (4 bytes), payload length (uint32 LE), sequence
(uint32 LE), monotonic timestamp in microseconds (uint64 LE), codec ID (uint8).
Codec IDs: 1 H.264, 2 MJPEG. Header length: 21 bytes. Maximum frame payload:
8 MiB. Multiple frames can be concatenated; reads may split anywhere.

The host parser rejects invalid headers and oversized frames. The envelope
does not yet define negotiated stream settings, retransmission, keyframe
requests, USB endpoints or CHDK PTP command numbers. Those need camera-side
investigation and versioning before deployment.

H.264 payload packetization and SPS/PPS handling remain unspecified. MJPEG
frame delimiter scanning is diagnostic only, not a substitute for JPEG decoding.

To test: `python -m unittest discover -s tests -v`.
