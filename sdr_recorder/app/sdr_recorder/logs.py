from __future__ import annotations

import logging
from collections import deque


class RingLogHandler(logging.Handler):
    def __init__(self, capacity: int = 300):
        super().__init__()
        self.lines: deque[str] = deque(maxlen=capacity)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))
