# PlutoSDR frequency recorder and Home Assistant add-on

The proven standalone Windows receiver remains in `record_pmr13.py`. A modular,
GitHub-installable Home Assistant add-on now lives in `sdr_recorder/`; see
[`sdr_recorder/README.md`](sdr_recorder/README.md) for installation and
[`sdr_recorder/ARCHITECTURE.md`](sdr_recorder/ARCHITECTURE.md) for the preserved
DSP baseline and runtime design.

Initial receive-only smoke test for a PlutoSDR-compatible Zynq/AD9363 board on Windows.

## Windows setup

1. Unplug the SDR.
2. Install the official **PlutoSDR-M2k USB drivers** from Analog Devices.
3. Install the current Windows **libiio** package from Analog Devices.
4. Reconnect the SDR using its USB data/OTG connector.
5. Confirm Device Manager shows working `IIO` and `RNDIS` devices, then run `iio_info -s`.
6. Install the Python packages:

   ```powershell
   python -m pip install -r requirements.txt
   ```

## Receive test

The default test tunes to 100 MHz and connects over Pluto's USB network interface:

```powershell
python test_pluto.py
```

Choose another known-safe receive frequency if required:

```powershell
python test_pluto.py --frequency 433920000
```

To use the native USB IIO backend, copy the URI reported by `iio_info -s`:

```powershell
python test_pluto.py --uri usb:1.2.5 --frequency 433920000
```

This script only receives. It does not enable or configure the transmitter.

## Record analogue PMR446 channel 13

Channel 13 is 446.15625 MHz. Record 60 seconds of narrow-FM voice to a WAV file:

```powershell
python record_pmr13.py
```

Choose the duration and output file if needed:

```powershell
python record_pmr13.py --duration 300 --output recordings\pmr13.wav
```

The recorder only writes audio while its RF squelch is open. Calibrate the
threshold by running this and keying a nearby channel-13 radio:

```powershell
python record_pmr13.py --calibrate --duration 20
```

Choose a threshold between the displayed idle and transmit levels, then record:

```powershell
python record_pmr13.py --duration 300 --squelch-dbfs -45
```

If a nearby transmitter produces an `OVERLOAD` warning, reduce `--rf-gain` or
move the transmitter farther from the SDR antenna.

By default no closed-squelch pre-roll is saved and only a 0.1-second tail is
kept after carrier loss. These can be changed with `--pre-roll` and `--hang`.

This is an analogue FM recorder. It will not decode digital PMR446. Only record
communications you are authorised to receive and retain.
