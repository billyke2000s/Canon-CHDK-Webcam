# Development

Requires Python 3.10+.

```sh
python -m unittest discover -s tests -v
python -m canon_webcam.cli --codec h264 --bitrate 30 --resolution 1920x1080 --fps 24
python -m canon_webcam.simulator --frames 48 --output synthetic.cwcm
python -m canon_webcam.inspect synthetic.cwcm
```

Synthetic packet files are intentionally not playable video and do not
indicate a camera connection. No dependencies are required for these tests.

## Protocol layering
- `stream.py`: hypothetical future compressed-frame envelope
- `mjpeg.py`: basic JPEG marker extraction (not a full decoder)
- `simulator.py`: synthetic envelope generator
- `inspect.py`: bounded-memory offline inspection
- `diagnostics.py`: basic throughput and sequence-gap metrics

Next integration milestone: implement and test a real CHDK PTP adapter using
verified protocol specifications, without confusing the CWCM envelope with
CHDK's existing live-view protocol.
