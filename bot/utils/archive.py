import zipfile
from pathlib import Path


def make_zip(files: list[Path], dest: Path) -> Path:
    """Fayllarni bitta ZIP arxivga joylaydi. Bir xil nomlarga raqam qo'shiladi."""
    used: set[str] = set()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            name, n = path.name, 1
            while name.lower() in used:
                name = f"{path.stem} ({n}){path.suffix}"
                n += 1
            used.add(name.lower())
            zf.write(path, arcname=name)
    return dest
