from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class SourceInfo:
    connected: bool = False
    description: str = ""
    error: str = ""


class IQSource(ABC):
    def __init__(self, center_hz: int, sample_rate_hz: int, gain_db: float, buffer_size: int = 65_536):
        self.center_hz = center_hz
        self.sample_rate_hz = sample_rate_hz
        self.gain_db = gain_db
        self.buffer_size = buffer_size
        self.info = SourceInfo()

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> np.ndarray: ...

    @abstractmethod
    def close(self) -> None: ...
