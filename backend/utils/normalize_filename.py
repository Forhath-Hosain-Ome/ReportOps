import re
from pathlib import Path

def normalize_filename(filename: str) -> str:
    name = Path(filename).stem
    ext = Path(filename).suffix.lower()

    # remove unsafe characters
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    # collapse multiple underscores
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "file"

    return f"{name}{ext}"