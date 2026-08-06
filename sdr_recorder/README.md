# SDR Radio Recorder add-on

A receive-only Home Assistant add-on for recording independent analogue NFM
channels from one wide PlutoSDR IQ stream. The add-on includes an Ingress UI,
SQLite recording index, generated mock input, and persistent media storage.

## Installation

1. Publish this repository to GitHub.
2. In Home Assistant, open **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
3. Add `https://github.com/timmchugh11/rtl-sdr-recorder--Home-Assistant`.
4. Install **SDR Radio Recorder**.
5. Start with `source: mock`, open the Web UI, and verify the generated channel
   activity and recordings.
6. Stop the add-on, select `source: pluto`, configure the URI and capture span,
   then start it again.

## SDR connection

The default hardware URI is `ip:192.168.2.1`, the standard Pluto USB-network
address. `ip:pluto.local` is also supported. A native libiio URI such as
`usb:1.2.5` can be used when USB forwarding exposes the IIO interface to the
add-on. The container includes libiio and requests USB access, but is not
privileged. The add-on never creates a TX buffer or changes a TX property.

Speech level and recording boundaries can be tuned from the add-on options:

- `audio_gain`: WAV output level after NFM demodulation (`0.08` by default).
- `pre_roll_seconds`: audio retained before squelch opens (`0.25` by default).
- `post_roll_seconds`: time to keep one recording open through brief carrier
  gaps and speech pauses (`2.0` by default).

Home Assistant preserves saved options during upgrades. When upgrading from
0.1.1 or earlier, set these values explicitly on the Configuration page.

The default 447.7 MHz centre and 4 MS/s rate nominally cover 445.7–449.7 MHz,
including all PMR446 channels and the editable 449 MHz project area. Frequencies
outside the usable Nyquist span are ignored with a clear log warning.

All 16 standard analogue PMR446 channels are prepopulated. Only the proven
PMR446 channel 13 is enabled on first start. Enable further channels from the
Frequency page after observing CPU headroom on the Home Assistant host.

> The Pluto and its transport must sustain the configured rate. Start with a
> smaller span if the Home Assistant host or USB/network link drops buffers.

## Recording storage

- Database and internal state: `/data/sdr_recorder.sqlite3`
- Audio: `/media/sdr_recorder/YYYY/MM/DD/`
- Interrupted active files: `*.partial.wav`; these are preserved as
  `*.recovered.wav` at the next start rather than deleted.

Home Assistant's writable media mapping makes audio persistent outside the
container. Filenames include UTC start time, safe friendly name, and frequency.

Retention by age and maximum storage is **disabled by default** (`0`). When
enabled it deletes oldest unprotected recordings only. Per-frequency retention
can override the global age. The UI can run configured retention manually.

## Home Assistant states and events

The add-on uses the automatically supplied Supervisor token—no long-lived token
is required. It publishes these transient states:

- `binary_sensor.sdr_connected`
- `binary_sensor.radio_receiving`
- `sensor.radio_active_frequency`
- `sensor.radio_recordings_today`
- `sensor.radio_storage_used`
- `sensor.radio_signal_strength`
- `switch.radio_receiver`

Events are named `sdr_recorder_transmission_started`,
`sdr_recorder_transmission_ended`, `sdr_recorder_recording_completed`,
`sdr_recorder_sdr_connected`, and `sdr_recorder_sdr_disconnected`.

These states are useful for dashboards and automations but are not durable
entity-registry entries. A companion Home Assistant integration or MQTT
discovery is the recommended next step for registered entities and native HA
services. Receiver controls are available in Ingress and the REST API now.

## Standalone test mode

From `sdr_recorder/app`, install `requirements.txt`, then use generated IQ:

```bash
python -m sdr_recorder.cli --source mock --duration 10 --output mock.wav
```

Or use the Pluto with the same receive/DSP module as the add-on:

```bash
python -m sdr_recorder.cli --source pluto --uri ip:192.168.2.1 \
  --frequency 446156250 --center 446156250 --sample-rate 1000000 \
  --gain-db 0 --duration 10 --output pluto.wav
```

The original repository-root `record_pmr13.py` is intentionally retained as
the proven Windows hardware reference.

## Initial limitations

- Analogue narrow FM only; digital PMR and CTCSS/DCS detection are not decoded.
- CPU use currently scales linearly with enabled channels. On the development
  CPU, 16 channels took 3.2× the realtime budget while approximately four fit.
  Channel 13 alone is therefore the safe initial default. A shared FFT/polyphase
  filter-bank channeliser is the recommended optimisation before enabling a
  large full-span plan on smaller Home Assistant hosts.
- The initial UI shows one active-channel waveform and a compact spectrum, not
  streamed audio monitoring.
- Recovered partial WAV files are preserved but not automatically indexed,
  because reliable metadata may not survive a hard container kill.
- Hardware operation and sustainable 4 MS/s multi-channel performance must be
  verified on the target Home Assistant host.
