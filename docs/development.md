# Development

Install Python 3.10+ with Tk, then:

```sh
python -m pip install -r requirements-desktop.txt -e . build twine ruff pip-audit
python -m unittest discover -s tests -v
python -m unittest discover -s firmware -p 'test_*.py' -v
python -m ruff check canon_webcam tests packaging
python -m canon_webcam.gui --self-test --report self-test.json
python -m build
python -m twine check dist/*
python -m pip_audit -r requirements-desktop.txt --progress-spinner off
```

The pinned desktop file chooses compatible PyAV versions per Python version. Core offline tools remain dependency-free; real USB, efficient decoding, GUI, recording and virtual camera need their respective project extras or the full desktop dependency set. Integration/encoding tests intentionally require desktop dependencies rather than silently skipping the core application path.

## Simulation and soak tests

`python -m canon_webcam.benchmark --seconds 300 --recording simulated.mkv` tests continuous producer/consumer scheduling and recording without USB. `--seconds` accepts up to 86400. The report includes measured cadence, queue drops, encoder bitrate and tracemalloc peak. Tracemalloc does **not** establish total process RSS or absence of native codec leaks; qualify process working set on Windows during the hardware soak. USB mode reports viewport payload rate, excluding USB headers and transport overhead; it is not a maximum bus-bandwidth test.

Unit tests cover real JPEG marker bytes, malformed CWCM framing, fragmented/coalesced PTP containers and ZLPs, transaction mismatch, DeviceInfo parsing, timeout poisoning, serial reconnect selection, viewport padding and signed chroma, slow sinks, disconnect recovery, preferences rollback, actual encoding/decoding and a synthetic PTP-to-recording integration.

## Windows packaging

Build on Windows; PyInstaller does not cross-compile a Windows executable from Linux:

```sh
python -m pip install -r requirements-desktop.txt -e . pyinstaller==6.22.3
python -m PyInstaller --clean --noconfirm packaging/windows.spec
```

Launch `dist/Canon-CHDK-Webcam/Canon-CHDK-Webcam.exe`. Keep the directory together. The executable supports `--self-test --report frozen-self-test.json` without displaying a window. The CI workflow builds on Linux/Windows Python 3.10/3.12, checks packaging and dependencies, then produces a Windows portable archive only after prerequisite checks pass. Tagged versions publish **experimental prereleases** only after required CI succeeds. A build or synthetic smoke success is not physical camera certification.

The package contains dynamically imported native dependencies and collected third-party license metadata. PyAV/FFmpeg builds including libx264 may carry GPL obligations; review distributed component licenses before redistributing binaries. No proprietary Canon firmware or OBS installer is included.
