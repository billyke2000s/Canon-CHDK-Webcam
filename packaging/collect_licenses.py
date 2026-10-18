"""Copy installed distribution notices and a dependency manifest to a bundle."""
from importlib.metadata import distributions
from pathlib import Path
import json
import shutil
import sys


def main():
    target = Path(sys.argv[1]) / "THIRD-PARTY-LICENSES"
    target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for dist in sorted(distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        manifest.append({"name": name, "version": dist.version,
                         "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", ""),
                         "homepage": dist.metadata.get("Home-page", "")})
        output = target / name
        output.mkdir(exist_ok=True)
        (output / "METADATA.txt").write_text(str(dist.metadata), encoding="utf-8")
        for file in dist.files or ():
            if any(word in file.name.lower() for word in ("license", "licence", "copying", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    # Preserve relative paths to avoid clobbering multiple license.txt files.
                    safe_parts = [part for part in file.parts if part not in ("..", ".", "/", "\\")]
                    destination = output.joinpath(*safe_parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    (target / "dependencies.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
