# Offline firmware evidence tools

No camera-side streaming firmware is implemented here. Do not flash this
directory or copy it onto an SD card as a CHDK distribution.

`inspect_dump.py` performs read-only CRC comparison of a local raw dump
against the known CHDK port's revision-specific source metadata. It has no
USB interface, patch command, arbitrary-memory function or network upload.

```console
python firmware/inspect_dump.py PRIMARY.BIN --base-address 0xff810000
python -m unittest firmware.test_inspect_dump
```

The base address must come from the dump's provenance; the example is not
a value to guess. A mismatch or missing CRC region prevents a match. A
matching dump only establishes the upstream CRC evidence, not safe hook
ownership or native streaming support.

See [the research record](../docs/firmware-research.md) for pinned sources,
port identity, unresolved encoder questions, prerequisites for later
experiments and recovery guidance. Stock upstream CHDK has its own build
instructions and firmware checks. No custom firmware build instructions
can honestly be provided until there is tested camera-side source to build.
