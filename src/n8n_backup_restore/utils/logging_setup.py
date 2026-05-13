from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from n8n_backup_restore.utils.files import ensure_dir


def build_logger(logs_dir: str) -> logging.Logger:
    logger = logging.getLogger("n8n_backup_restore")
    if logger.handlers:
        return logger

    ensure_dir(logs_dir)
    date_str = datetime.now().strftime("%Y%m%d")
    file_path = Path(logs_dir) / f"app_{date_str}.log"

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    fh = logging.FileHandler(file_path, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger
