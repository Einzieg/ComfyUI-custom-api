"""Build an installable archive from an explicit allowlist, never bundling secrets."""
from pathlib import Path
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ALLOW = ["__init__.py", "custom_api", "web", "locales", "README.md", "requirements.txt", "pyproject.toml", "LICENSE", "docs", "example_workflows"]

version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
output = ROOT / "dist" / f"ComfyUI-custom-api-{version}.zip"
output.parent.mkdir(exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for item in ALLOW:
        source = ROOT / item
        paths = source.rglob("*") if source.is_dir() else [source]
        for path in sorted(paths):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"):
                archive.write(path, "ComfyUI-custom-api/" + path.relative_to(ROOT).as_posix())
print(output)
