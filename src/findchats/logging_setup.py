from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def setup_logging(log_level: str, log_dir: str) -> Path:
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    dated_log_file = log_path / f"{datetime.now().date().isoformat()}.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(dated_log_file, encoding="utf-8")
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    return dated_log_file
