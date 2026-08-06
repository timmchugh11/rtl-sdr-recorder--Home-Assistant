import numpy as np

from sdr_recorder.dsp import NFMChannel


def nfm(rate, frequency, center, samples, amplitude=500):
    t = np.arange(samples) / rate
    phase = 2 * np.pi * (frequency - center) * t + 2.5 * np.sin(2 * np.pi * 1000 * t)
    return (amplitude * np.exp(1j * phase)).astype(np.complex64)


def test_nfm_channel_opens_and_demodulates():
    rate = 1_000_000
    frequency = 446_156_250
    channel = NFMChannel(frequency, frequency, rate, 10_000, -45)
    result = channel.process(nfm(rate, frequency, frequency, 65_536), 0)
    assert result.carrier
    assert result.signal_dbfs > -20
    assert len(result.audio) > 500
    assert np.max(np.abs(result.audio)) > 0.01


def test_nfm_channel_stays_closed_on_low_noise():
    rng = np.random.default_rng(1)
    raw = (rng.normal(0, .2, 65_536) + 1j * rng.normal(0, .2, 65_536)).astype(np.complex64)
    channel = NFMChannel(446_156_250, 446_156_250, 1_000_000, 10_000, -45)
    assert not channel.process(raw, 0).carrier
