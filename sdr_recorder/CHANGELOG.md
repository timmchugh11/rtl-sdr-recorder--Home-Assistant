# Changelog

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
