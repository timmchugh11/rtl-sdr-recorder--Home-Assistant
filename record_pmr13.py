"""Record analogue PMR446 channel 13 as a mono WAV file (receive only)."""

from __future__ import annotations

import argparse
from collections import deque
import datetime as dt
import sys
import wave
from pathlib import Path

import numpy as np
from scipy import signal


FREQUENCY_HZ = 446_156_250
SDR_SAMPLE_RATE = 1_000_000
FM_SAMPLE_RATE = 50_000
AUDIO_SAMPLE_RATE = 10_000


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default="ip:192.168.2.1", help="Pluto IIO URI")
    parser.add_argument("--duration", type=float, default=60, help="Recording length in seconds")
    parser.add_argument("--output", type=Path, help="Output WAV path")
    parser.add_argument("--gain", type=float, default=0.2, help="Audio gain (default: 0.2)")
    parser.add_argument("--rf-gain", type=float, default=0, help="Manual receiver gain in dB")
    parser.add_argument(
        "--squelch-dbfs", type=float, default=-45, help="Open squelch at this RF level in dBFS"
    )
    parser.add_argument("--hang", type=float, default=0.1, help="Seconds to hold open after carrier drops")
    parser.add_argument("--pre-roll", type=float, default=0.0, help="Seconds retained before squelch opens")
    parser.add_argument(
        "--calibrate", action="store_true", help="Display RF level only; do not create a WAV"
    )
    return parser.parse_args()


def pcm16(audio: np.ndarray, gain: float) -> bytes:
    # FM discriminator output is radians/sample. Remove residual carrier offset,
    # then apply a fixed gain without automatic level pumping between chunks.
    audio = audio - np.mean(audio)
    audio = np.clip(audio * gain, -1.0, 1.0)
    return (audio * 32767).astype("<i2").tobytes()


def main() -> int:
    args = arguments()
    if args.duration <= 0:
        print("--duration must be greater than zero", file=sys.stderr)
        return 2


    try:
        import adi
    except Exception as exc:
        print(f"Could not load pyadi-iio/libiio: {exc}", file=sys.stderr)
        print("Install the ADI Windows libiio package, then reopen PowerShell.", file=sys.stderr)
        return 2

    output = args.output or Path(
        f"pmr13-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.wav"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        radio = adi.Pluto(uri=args.uri)
        radio.sample_rate = SDR_SAMPLE_RATE
        radio.rx_lo = FREQUENCY_HZ
        # The AD9363 analogue filter cannot be as narrow as a PMR channel; the
        # digital filters below provide the required voice-channel selectivity.
        radio.rx_rf_bandwidth = 200_000
        # A short buffer gives squelch approximately 65 ms response time.
        radio.rx_buffer_size = 65_536
        # A fixed gain makes the RF power threshold stable; AGC would raise the
        # noise floor whenever the channel is idle and defeat energy squelch.
        radio.gain_control_mode_chan0 = "manual"
        radio.rx_hardwaregain_chan0 = args.rf_gain
    except Exception as exc:
        print(f"Could not configure Pluto: {exc}", file=sys.stderr)
        return 1

    # Select the 12.5 kHz NFM channel before demodulation. Stateful filtering
    # avoids the discontinuities caused by independently resampling each block.
    iq_decimation = SDR_SAMPLE_RATE // FM_SAMPLE_RATE
    channel_taps = signal.firwin(401, 8_000, fs=SDR_SAMPLE_RATE)
    channel_state = np.zeros(len(channel_taps) - 1, dtype=np.complex64)
    iq_input_count = 0

    # Voice band filtering after FM demodulation, then integer audio decimation.
    audio_decimation = FM_SAMPLE_RATE // AUDIO_SAMPLE_RATE
    voice_sos = signal.butter(
        6, (300, 3_000), btype="bandpass", fs=FM_SAMPLE_RATE, output="sos"
    )
    voice_state = signal.sosfilt_zi(voice_sos) * 0
    audio_input_count = 0
    previous_iq: complex | None = None
    written = 0
    elapsed_samples = 0
    target = round(args.duration * AUDIO_SAMPLE_RATE)
    chunk_seconds = radio.rx_buffer_size / SDR_SAMPLE_RATE
    pre_roll: deque[np.ndarray] = deque(maxlen=max(0, round(args.pre_roll / chunk_seconds)))
    squelch_open = False
    hang_left = 0.0

    print(f"Recording analogue PMR446 channel 13 ({FREQUENCY_HZ / 1e6:.5f} MHz)")
    print(f"Source: {args.uri}; RF gain: {args.rf_gain:.1f} dB")
    if args.calibrate:
        print("Calibration: key the test radio and compare IDLE with TX levels (no WAV is written).")
    else:
        print(f"Squelch: {args.squelch_dbfs:.1f} dBFS; output: {output}")

    try:
        wav = None if args.calibrate else wave.open(str(output), "wb")
        if wav is not None:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(AUDIO_SAMPLE_RATE)

        while elapsed_samples < target:
                raw_iq = np.asarray(radio.rx(), dtype=np.complex64)
                rms = float(np.sqrt(np.mean(np.abs(raw_iq) ** 2)))
                rf_dbfs = 20 * np.log10(max(rms, 1e-12) / 2048.0)
                if args.calibrate:
                    elapsed_samples += round(chunk_seconds * AUDIO_SAMPLE_RATE)
                    print(f"\rRF level: {rf_dbfs:7.2f} dBFS", end="")
                    continue

                # Channel filter and decimate 1 MHz IQ to 50 kHz while keeping
                # filter and decimation phase continuous across SDR buffers.
                filtered_iq, channel_state = signal.lfilter(
                    channel_taps, [1.0], raw_iq, zi=channel_state
                )
                iq_start = (-iq_input_count) % iq_decimation
                iq = filtered_iq[iq_start::iq_decimation]
                iq_input_count += len(raw_iq)
                if previous_iq is not None:
                    iq = np.concatenate(([previous_iq], iq))
                previous_iq = complex(iq[-1])
                audio = np.angle(iq[1:] * np.conj(iq[:-1])).astype(np.float32)
                audio, voice_state = signal.sosfilt(voice_sos, audio, zi=voice_state)
                audio_start = (-audio_input_count) % audio_decimation
                audio_input_count += len(audio)
                audio = audio[audio_start::audio_decimation]
                audio = audio[: target - elapsed_samples]
                elapsed_samples += len(audio)

                carrier = rf_dbfs >= args.squelch_dbfs
                if carrier:
                    hang_left = args.hang
                    if not squelch_open:
                        squelch_open = True
                        for buffered in pre_roll:
                            wav.writeframesraw(pcm16(buffered, args.gain))
                            written += len(buffered)
                        pre_roll.clear()

                if squelch_open:
                    wav.writeframesraw(pcm16(audio, args.gain))
                    written += len(audio)
                    if not carrier:
                        hang_left -= len(audio) / AUDIO_SAMPLE_RATE
                        if hang_left <= 0:
                            squelch_open = False
                else:
                    pre_roll.append(audio.copy())

                state = "OPEN  " if squelch_open else "closed"
                overload = " OVERLOAD" if rf_dbfs > -6 else ""
                print(
                    f"\rElapsed {elapsed_samples / AUDIO_SAMPLE_RATE:6.1f}/{args.duration:.1f} s | "
                    f"RF {rf_dbfs:7.2f} dBFS{overload} | {state} | "
                    f"saved {written / AUDIO_SAMPLE_RATE:5.1f} s",
                    end="",
                )
        if wav is not None:
            wav.close()
    except KeyboardInterrupt:
        print("\nStopped early; finalising WAV file.")
    except Exception as exc:
        print(f"\nRecording failed: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            radio.rx_destroy_buffer()
        except Exception:
            pass

    if args.calibrate:
        print("\nCalibration finished.")
    else:
        print(f"\nSaved {written / AUDIO_SAMPLE_RATE:.1f} seconds of open-squelch audio to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
