from __future__ import annotations

import logging
import os
import queue
import threading

import httpx

LOG = logging.getLogger(__name__)


class HomeAssistantPublisher:
    """Publishes events and transient states with the add-on Supervisor token."""

    def __init__(self):
        self.token = os.getenv("SUPERVISOR_TOKEN", "")
        self.base = os.getenv("SUPERVISOR_API", "http://supervisor/core/api")
        self.queue: queue.Queue = queue.Queue(maxsize=256)
        self.stop_marker = object()
        self.thread = threading.Thread(target=self._run, name="ha-publisher", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.queue.put(self.stop_marker)
        self.thread.join(timeout=5)

    def event(self, name: str, data: dict) -> None:
        if self.token:
            try: self.queue.put_nowait(("event", name, data))
            except queue.Full: LOG.warning("Home Assistant event queue full")

    def states(self, receiver: dict, stats: dict) -> None:
        states = {
            "binary_sensor.sdr_connected": ("on" if receiver["connected"] else "off", {"friendly_name": "SDR Connected"}),
            "binary_sensor.radio_receiving": ("on" if receiver["active_frequency_hz"] else "off", {"friendly_name": "Radio Receiving"}),
            "sensor.radio_active_frequency": (receiver["active_frequency_hz"] or "unknown", {"friendly_name": "Radio Active Frequency", "unit_of_measurement": "Hz"}),
            "sensor.radio_recordings_today": (stats["recordings_today"], {"friendly_name": "Radio Recordings Today"}),
            "sensor.radio_storage_used": (round(stats["storage_used_bytes"] / 1048576, 2), {"friendly_name": "Radio Storage Used", "unit_of_measurement": "MB"}),
            "sensor.radio_signal_strength": (receiver["signal_dbfs"], {"friendly_name": "Radio Signal Strength", "unit_of_measurement": "dBFS"}),
            "switch.radio_receiver": ("on" if receiver["running"] else "off", {"friendly_name": "Radio Receiver"}),
        }
        if self.token:
            try: self.queue.put_nowait(("states", states))
            except queue.Full: pass

    def _run(self) -> None:
        if not self.token:
            LOG.info("No Supervisor token; Home Assistant states/events disabled in local mode")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        with httpx.Client(headers=headers, timeout=5) as client:
            while True:
                item = self.queue.get()
                if item is self.stop_marker: return
                try:
                    if item[0] == "event":
                        client.post(f"{self.base}/events/sdr_recorder_{item[1]}", json=item[2]).raise_for_status()
                    else:
                        for entity_id, (state, attributes) in item[1].items():
                            client.post(f"{self.base}/states/{entity_id}", json={"state": state, "attributes": attributes}).raise_for_status()
                except Exception as exc:
                    LOG.warning("Home Assistant publish failed: %s", exc)
