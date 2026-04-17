from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from src.config import settings


class AppLogger:
    def __init__(self) -> None:
        self.path = Path(settings.app_log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.counters: Counter[str] = Counter()
        self.logger = logging.getLogger("aegisai")
        if not self.logger.handlers:
            try:
                handler = logging.FileHandler(self.path, encoding="utf-8")
            except Exception:
                handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
            self.logger.propagate = False

    def log(self, event: str, **payload: Any) -> None:
        try:
            self.counters[event] += 1
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **payload,
            }
            line = json.dumps(record, ensure_ascii=True, default=str)
            with self.lock:
                self.logger.info(line)
        except Exception:
            return

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        records: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        return records


app_logger = AppLogger()

