"""Build on Windows: python -m PyInstaller --clean packaging/windows.spec."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
datas = []
binaries = []
hiddenimports = ["PIL.ImageTk", "usb.backend.libusb1"]
# These dependencies are imported dynamically by optional runtime backends.
# Include their native DLLs, extension modules, and metadata explicitly.
for package, distribution in (("av", "av"), ("numpy", "numpy"), ("PIL", "Pillow"),
                              ("pyvirtualcam", "pyvirtualcam"), ("usb", "pyusb"),
                              ("libusb_package", "libusb-package")):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas + copy_metadata(distribution)
    binaries += package_binaries
    hiddenimports += package_imports
analysis = Analysis([str(root / "packaging" / "entrypoint.py")], pathex=[str(root)],
                    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
                    excludes=["pytest", "numpy.tests"], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
          name="Canon-CHDK-Webcam", console=False, upx=False)
app = COLLECT(exe, analysis.binaries, analysis.datas,
              name="Canon-CHDK-Webcam", upx=False)
