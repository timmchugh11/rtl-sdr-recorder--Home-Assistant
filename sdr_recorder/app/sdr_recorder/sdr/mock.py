from __future__ import annotations

import time

import numpy as np

from .base import IQSource


class MockSource(IQSource):
    """Realtime generated NFM carriers for UI and recording development."""

    def __init__(self, center_hz: int, sample_rate_hz: int, gain_db: float,
                 frequencies: list[int] | None = None, buffer_size: int = 65_536):
        super().__init__(center_hz, sample_rate_hz, gain_db, buffer_size)
        self.frequencies = frequencies or [446_006_250, 446_156_250]
        self._sample_index = 0
        self._started = 0.0
        self._rng = np.random.default_rng(446)

    def open(self) -> None:
        self._started = time.monotonic()
        self.info.connected = True
        self.info.description = "Generated mock NFM input"
        self.info.error = ""

    def read(self) -> np.ndarray:
        if not self.info.connected:
            raise RuntimeError("Mock source is not open")
        n = np.arange(self.buffer_size, dtype=np.float64) + self._sample_index
        seconds = n / self.sample_rate_hz
        iq = (self._rng.normal(0, 0.35, self.buffer_size) +
              1j * self._rng.normal(0, 0.35, self.buffer_size)).astype(np.complex64)
        elapsed = time.monotonic() - self._started
        slot = int(elapsed // 4) % (len(self.frequencies) + 1)
        if slot < len(self.frequencies) and elapsed % 4 < 2.3:
            offset = self.frequencies[slot] - self.center_hz
            voice = 850 + slot * 230
            phase = 2 * np.pi * offset * seconds + 2.8 * np.sin(2 * np.pi * voice * seconds)
            iq += (450 * np.exp(1j * phase)).astype(np.complex64)
        self._sample_index += self.buffer_size
        time.sleep(self.buffer_size / self.sample_rate_hz)
        return iq

    def close(self) -> None:
        self.info.connected = False
