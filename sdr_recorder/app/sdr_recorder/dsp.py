from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal


@dataclass(slots=True)
class ChannelResult:
    audio: np.ndarray
    signal_dbfs: float
    carrier: bool
    waveform: list[float]


class NFMChannel:
    """Stateful per-frequency mixer, channel filter and proven NFM demodulator."""

    FM_RATE = 50_000

    def __init__(self, frequency_hz: int, center_hz: int, input_rate: int,
                 audio_rate: int, squelch_dbfs: float, audio_gain: float = 0.2):
        if input_rate % self.FM_RATE or self.FM_RATE % audio_rate:
            raise ValueError("Sample rates must divide cleanly into 50 kHz and the audio rate")
        self.frequency_hz = frequency_hz
        self.center_hz = center_hz
        self.input_rate = input_rate
        self.audio_rate = audio_rate
        self.squelch_dbfs = squelch_dbfs
        self.audio_gain = audio_gain
        # Preserve the exact hardware-tested PMR13 pipeline when a 1 MS/s
        # capture is centred on the selected channel. The wideband channeliser
        # remains available when several offset channels are configured.
        self._proven_direct = input_rate == 1_000_000 and frequency_hz == center_hz
        if self._proven_direct:
            self._direct_taps = signal.firwin(401, 8_000, fs=input_rate)
            self._direct_state = np.zeros(len(self._direct_taps) - 1, dtype=np.complex64)
        total_decimation = input_rate // self.FM_RATE
        # Keep the final FIR near 200 kS/s. The wide-rate IIR cheaply rejects
        # energy that would alias in the first stage; the narrow FIR preserves
        # the proven 8 kHz NFM channel shape.
        self._coarse_decimation = max(1, total_decimation // 4)
        self._fine_rate = input_rate // self._coarse_decimation
        self._fine_decimation = self._fine_rate // self.FM_RATE
        self._coarse_sos = signal.butter(6, 20_000, btype="lowpass", fs=input_rate, output="sos")
        self._coarse_state = np.zeros((self._coarse_sos.shape[0], 2), dtype=np.complex64)
        # A 12.5 kHz PMR channel has a 6.25 kHz half-width. The long Kaiser FIR
        # prevents a strong carrier from opening neighbouring channel squelches.
        self._channel_taps = signal.firwin(301, 6_000, fs=self._fine_rate,
                                           window=("kaiser", 8.6))
        self._channel_state = np.zeros(len(self._channel_taps) - 1, dtype=np.complex64)
        self._voice_sos = signal.butter(6, (300, 3_000), btype="bandpass",
                                        fs=self.FM_RATE, output="sos")
        self._voice_state = signal.sosfilt_zi(self._voice_sos) * 0
        self._audio_decimation = self.FM_RATE // audio_rate
        self._input_count = 0
        self._fine_count = 0
        self._audio_count = 0
        self._previous_iq: complex | None = None
        self._mix_offset = self.frequency_hz - self.center_hz
        self._mix_block: np.ndarray | None = None
        self._mix_phase = 1.0 + 0.0j
        self._mix_step = np.exp(-2j * np.pi * self._mix_offset / self.input_rate)

    def process(self, raw: np.ndarray, first_sample: int) -> ChannelResult:
        if self._proven_direct:
            # This matches record_pmr13.py: measure raw RF power, then apply a
            # stateful 8 kHz FIR and decimate directly from 1 MHz to 50 kHz.
            rms = float(np.sqrt(np.mean(np.abs(raw) ** 2))) if raw.size else 0.0
            filtered, self._direct_state = signal.lfilter(
                self._direct_taps, [1.0], raw, zi=self._direct_state
            )
            start = (-self._input_count) % (self.input_rate // self.FM_RATE)
            channel_iq = filtered[start::self.input_rate // self.FM_RATE]
            self._input_count += len(raw)
        else:
            # SDR block lengths are stable. Cache one NCO block rather than
            # evaluating millions of complex exponentials per channel for
            # every read; carry only a scalar phase between blocks.
            if self._mix_block is None or len(self._mix_block) != len(raw):
                self._mix_block = np.power(
                    self._mix_step, np.arange(len(raw), dtype=np.int64)
                ).astype(np.complex64)
            mixed = raw * (self._mix_block * self._mix_phase)
            self._mix_phase *= self._mix_step ** len(raw)
            self._mix_phase /= abs(self._mix_phase)
            coarse, self._coarse_state = signal.sosfilt(self._coarse_sos, mixed, zi=self._coarse_state)
            start = (-self._input_count) % self._coarse_decimation
            coarse = coarse[start::self._coarse_decimation]
            self._input_count += len(raw)
            filtered, self._channel_state = signal.lfilter(
                self._channel_taps, [1.0], coarse, zi=self._channel_state
            )
            start = (-self._fine_count) % self._fine_decimation
            channel_iq = filtered[start::self._fine_decimation]
            self._fine_count += len(coarse)
            rms = float(np.sqrt(np.mean(np.abs(channel_iq) ** 2))) if channel_iq.size else 0.0
        level = float(20 * np.log10(max(rms, 1e-12) / 2048.0))
        if self._previous_iq is not None:
            channel_iq = np.concatenate(([self._previous_iq], channel_iq))
        if not channel_iq.size:
            return ChannelResult(np.empty(0, np.float32), level, False, [])
        self._previous_iq = complex(channel_iq[-1])
        audio = np.angle(channel_iq[1:] * np.conj(channel_iq[:-1])).astype(np.float32)
        audio, self._voice_state = signal.sosfilt(self._voice_sos, audio, zi=self._voice_state)
        start = (-self._audio_count) % self._audio_decimation
        self._audio_count += len(audio)
        audio = audio[start::self._audio_decimation]
        audio -= np.mean(audio) if audio.size else 0
        audio = np.clip(audio * self.audio_gain, -1, 1).astype(np.float32)
        stride = max(1, len(audio) // 160)
        waveform = audio[::stride][:160].astype(float).tolist()
        return ChannelResult(audio, level, level >= self.squelch_dbfs, waveform)
