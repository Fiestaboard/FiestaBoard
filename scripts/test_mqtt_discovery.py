#!/usr/bin/env python3
"""Publish MQTT discovery messages to a broker using raw sockets.

Uses the existing src.mqtt.discovery module to generate HA-compatible
discovery payloads, then publishes them to Mosquitto so Home Assistant
can auto-discover FiestaBoard.

Usage (from inside the dev container):
    python scripts/test_mqtt_discovery.py [--broker mosquitto] [--port 1883]

This script requires no extra dependencies (no paho-mqtt). It speaks
just enough MQTT v3.1.1 to send CONNECT, PUBLISH (QoS 0, retained),
and DISCONNECT.
"""

import argparse
import json
import socket
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mqtt.config import MQTTConfig
from src.mqtt.discovery import build_all_discovery_messages


# ---------------------------------------------------------------------------
# Minimal MQTT 3.1.1 helpers (only what we need: CONNECT, PUBLISH, DISCONNECT)
# ---------------------------------------------------------------------------

def _encode_utf8(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return struct.pack("!H", len(encoded)) + encoded


def _encode_remaining_length(length: int) -> bytes:
    out = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length > 0:
            byte |= 0x80
        out.append(byte)
        if length == 0:
            break
    return bytes(out)


def _make_connect(client_id: str = "fiestaboard-test") -> bytes:
    variable = (
        _encode_utf8("MQTT")           # Protocol name
        + struct.pack("!B", 4)         # Protocol level 4 = MQTT 3.1.1
        + struct.pack("!B", 0x02)      # Connect flags: clean session
        + struct.pack("!H", 60)        # Keep alive 60s
    )
    payload = _encode_utf8(client_id)
    remaining = variable + payload
    return bytes([0x10]) + _encode_remaining_length(len(remaining)) + remaining


def _make_publish(topic: str, payload_str: str, retain: bool = True) -> bytes:
    topic_bytes = _encode_utf8(topic)
    payload_bytes = payload_str.encode("utf-8")
    flags = 0x30  # PUBLISH, QoS 0
    if retain:
        flags |= 0x01
    remaining = topic_bytes + payload_bytes
    return bytes([flags]) + _encode_remaining_length(len(remaining)) + remaining


def _make_disconnect() -> bytes:
    return bytes([0xE0, 0x00])


def publish_discovery(broker_host: str, broker_port: int) -> bool:
    config = MQTTConfig(
        enabled=True,
        broker_host=broker_host,
        broker_port=broker_port,
        discovery_prefix="homeassistant",
        base_topic="fiestaboard",
        instance_id="fiestaboard_1",
    )

    # Use FIESTABOARD_EXTERNAL_URL if set, otherwise default to the standard
    # host-accessible address for local dev.
    external_url = os.environ.get("FIESTABOARD_EXTERNAL_URL", "http://localhost:4420")

    messages = build_all_discovery_messages(
        config,
        sw_version="2.7.0",
        configuration_url=external_url,
        page_names=["Morning", "Weather", "Sports"],
    )

    print(f"Connecting to MQTT broker at {broker_host}:{broker_port}...")

    sock = socket.create_connection((broker_host, broker_port), timeout=5)
    try:
        # CONNECT
        sock.sendall(_make_connect())
        connack = sock.recv(4)
        if len(connack) < 4 or connack[3] != 0:
            print(f"CONNACK failed: {connack.hex()}")
            return False
        print("Connected to broker.")

        # Publish availability first
        avail_topic = f"{config.base_topic}/status"
        sock.sendall(_make_publish(avail_topic, "online"))
        print(f"  Published: {avail_topic} -> online")

        # Publish all discovery messages
        for msg in messages:
            topic = msg["topic"]
            payload = msg["payload"]
            sock.sendall(_make_publish(topic, payload))
            parsed = json.loads(payload)
            print(f"  Published: {topic}")
            print(f"    -> name={parsed.get('name')}, unique_id={parsed.get('unique_id')}")

        # Publish some initial state values so entities appear with data
        states = {
            "schedule_enabled": "ON",
            "display_service": "ON",
            "active_page": "Weather",
            "transition_style": "column",
            "current_page": "Weather",
            "service_status": "ON",
            "current_message": "HELLO WORLD",
            "silence_mode": "OFF",
            "version": "2.7.0",
            "page_count": "3",
            "refresh_interval": "300",
        }
        for obj_id, value in states.items():
            state_topic = f"{config.base_topic}/{obj_id}/state"
            sock.sendall(_make_publish(state_topic, value))
            print(f"  State: {state_topic} -> {value}")

        # DISCONNECT
        sock.sendall(_make_disconnect())
        print(f"\nDone! Published {len(messages)} discovery messages + {len(states)} state values.")
        print("Check Home Assistant -> Settings -> Devices -> search 'FiestaBoard'")
        return True

    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Publish FiestaBoard MQTT discovery messages")
    parser.add_argument("--broker", default="mosquitto", help="MQTT broker host (default: mosquitto)")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    args = parser.parse_args()

    success = publish_discovery(args.broker, args.port)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
