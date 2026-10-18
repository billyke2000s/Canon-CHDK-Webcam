"""Frozen application entry point, including GUI's headless --self-test mode."""
from canon_webcam.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
