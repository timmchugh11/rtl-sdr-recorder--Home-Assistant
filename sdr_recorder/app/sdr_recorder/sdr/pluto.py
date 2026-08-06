from __future__ import annotations

import numpy as np

from .base import IQSource


class PlutoSource(IQSource):
    """Receive-only Pluto source. No TX object, buffer or attribute is touched."""

    def __init__(self, uri: str, center_hz: int, sample_rate_hz: int, bandwidth_hz: int,
                 gain_mode: str, gain_db: float, buffer_size: int = 65_536):
        super().__init__(center_hz, sample_rate_hz, gain_db, buffer_size)
        self.uri = uri
        self.bandwidth_hz = bandwidth_hz
        self.gain_mode = gain_mode
        self._radio = None

    def open(self) -> None:
        import adi

        radio = adi.Pluto(uri=self.uri)
        radio.sample_rate = self.sample_rate_hz
        radio.rx_lo = self.center_hz
        radio.rx_rf_bandwidth = self.bandwidth_hz
        radio.rx_buffer_size = self.buffer_size
        radio.gain_control_mode_chan0 = self.gain_mode
        if self.gain_mode == "manual":
            radio.rx_hardwaregain_chan0 = self.gain_db
        self._radio = radio
        self.info.connected = True
        self.info.description = f"PlutoSDR at {self.uri}"
        self.info.error = ""

    def read(self) -> np.ndarray:
        if self._radio is None:
            raise RuntimeError("Pluto source is not open")
        return np.asarray(self._radio.rx(), dtype=np.complex64)

    def close(self) -> None:
        if self._radio is not None:
            try:
                self._radio.rx_destroy_buffer()
            finally:
                self._radio = None
        self.info.connected = False
