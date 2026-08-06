# Architecture and proven receiver baseline

## Preserved baseline

The repository-root `record_pmr13.py` was proven locally with the connected
Pluto-compatible Zynq/AD9363 board. Its successful signal path is:

1. `adi.Pluto(uri="ip:192.168.2.1")`, receive properties only.
2. Fixed manual RX gain and a 65,536-sample buffer.
3. Stateful channel selection around a PMR carrier.
4. 50 kS/s complex IQ before the phase-difference FM discriminator.
5. 300–3,000 Hz sixth-order voice filter.
6. 10 kHz, 16-bit mono PCM WAV.
7. RF-level squelch with configurable pre/post-roll.

The add-on keeps those values in `dsp.NFMChannel`. For a wide input it adds a
coarse stateful decimation stage before the same 8 kHz narrow filter, avoiding
the earlier unsuccessful direct-to-audio-rate FM processing.

## Runtime data flow

```text
PlutoSource / MockSource
        │ one wide complex64 IQ stream
        ▼
ReceiverEngine thread
        ├─ spectrum snapshot
        ├─ NFMChannel(frequency A) ─ squelch/session A ─┐
        ├─ NFMChannel(frequency B) ─ squelch/session B ─┼─ bounded command queue
        └─ NFMChannel(frequency N) ─ squelch/session N ─┘
                                                       ▼
                                              RecordingWorker thread
                                              WAV + atomic finalise + SQLite

FastAPI/Ingress ◀── lock-protected compact status snapshots
Home Assistant ◀── non-blocking publisher queue and Supervisor token
```

The receiver is independent of browser connections. WebSockets carry compact
live state, spectrum bins, and waveform points. Audio files are served from disk
with `FileResponse`, not loaded into application memory.
