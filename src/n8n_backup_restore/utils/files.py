from __future__ import annotations

import re
from pathlib import Path


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MULTISPACE = re.compile(r"\s+")


def sanitize_filename(value: str, fallback: str = "sem_nome") -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", value.strip())
    cleaned = MULTISPACE.sub(" ", cleaned).strip(" .")
    return cleaned if cleaned else fallback


def ensure_dir(path: str | Path) -> Path:
    result = Path(path)
    result.mkdir(parents=True, exist_ok=True)
    return result
