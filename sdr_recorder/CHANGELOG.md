# Changelog

## 0.3.0

- Add persistent per-frequency tuning correction in hertz.
- Apply correction in each independent digital down-converter before filtering.
- Seed measured corrections for PMR13, 449.312500, and 449.400000 MHz.
- Default to the verified PMR13/449.400 two-channel 4 MS/s capture span.
- Show and edit tuning correction from the Ingress Frequency page.

## 0.2.3

- Make the proven centred PMR446 Channel 13 capture the first-run default.
- Prevent a reinstall from silently returning to the experimental 4 MS/s
  wideband demodulation path.

## 0.2.2

- Use the exact proven PMR demodulation pipeline for a centred 1 MS/s channel.
- Correct live status after changing centre frequency, sample rate, or gain.

## 0.2.1

- Buffer brief squelch detector dropouts instead of replacing speech blocks
  immediately with silence.
- Confirm sustained carrier loss before gating RF noise.
- Synchronise the backend version reported by diagnostics with the add-on.

## 0.2.0

- Add editable receiver, audio, pre/post-roll, and retention settings to Ingress.
- Persist application settings under `/data/receiver_settings.json`.
- Reduce Supervisor configuration to SDR source and device URI only.
- Apply DSP changes with a clean automatic receiver restart.

## 0.1.2

- Lower the default NFM audio gain to prevent loud, clipped recordings.
- Make audio gain configurable from the add-on options.
- Increase the default post-roll to two seconds so normal pauses do not split an announcement.

## 0.1.1

- Fix Home Assistant local builds by pinning the Dockerfile directly to the
  multi-architecture Debian Python image. Supervisor can no longer substitute
  its Alpine base, where `apt-get` and packaged libiio are unavailable.
- Remove the ambiguous `BUILD_FROM` argument and its Docker warning.

## 0.1.0

- Initial GitHub-installable add-on.
- Receive-only PlutoSDR and generated mock IQ sources.
- One wide IQ stream with independent NFM channel processing and squelch.
- SQLite recording index, safe media storage, protection and opt-in retention.
- Ingress receiver, recording library, frequency management and diagnostics pages.
- Home Assistant state and event publishing through the Supervisor token.
