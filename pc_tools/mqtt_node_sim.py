#!/usr/bin/env python3
"""
Project A MQTT node simulator.

Publishes:
- telemetry: projectA/node/{node_id}/telemetry
- event:     projectA/node/{node_id}/event
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import uuid

try:
    import paho.mqtt.client as mqtt
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "paho-mqtt is required for mqtt_node_sim.py. Install: py -m pip install paho-mqtt"
    ) from e


def _simulate_values(t: float, rng: random.Random):
    temp = 25.5 + 2.2 * math.sin(t / 45.0) + rng.uniform(-0.2, 0.2)
    hum = 55.0 + 8.0 * math.sin(t / 60.0 + 0.7) + rng.uniform(-0.6, 0.6)
    dist = 760.0 + 260.0 * math.sin(t / 22.0 + 0.3) + rng.uniform(-16.0, 16.0)
    curr = 930.0 + 220.0 * math.sin(t / 18.0 + 1.2) + rng.uniform(-22.0, 22.0)
    return temp, hum, dist, curr


def main() -> int:
    parser = argparse.ArgumentParser(description="Project A MQTT node simulator")
    parser.add_argument("--node-id", default="esp32_sim_01")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--topic-root", default="projectA")
    parser.add_argument("--interval-ms", type=int, default=500)
    parser.add_argument("--runtime-s", type=float, default=120.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inject-anomaly-every-s", type=float, default=20.0)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    client = mqtt.Client(client_id=f"projectA-node-{args.node_id}")
    client.connect(args.mqtt_host, args.mqtt_port, keepalive=30)
    client.loop_start()

    t0 = time.time()
    next_anomaly = t0 + max(2.0, args.inject_anomaly_every_s)
    seq = 0
    try:
        while True:
            now = time.time()
            elapsed = now - t0
            if args.runtime_s > 0 and elapsed >= args.runtime_s:
                break

            temp, hum, dist, curr = _simulate_values(elapsed, rng)
            inject = now >= next_anomaly
            if inject:
                # Controlled anomaly injection: abrupt distance drop + current spike.
                dist = max(80.0, dist - rng.uniform(350.0, 520.0))
                curr = curr + rng.uniform(350.0, 520.0)
                next_anomaly = now + max(2.0, args.inject_anomaly_every_s)

            telemetry = {
                "ts": now,
                "node_id": args.node_id,
                "temp_c": round(temp, 2),
                "hum_rh": round(hum, 2),
                "dist_mm": round(dist, 1),
                "curr_ma": round(curr, 1),
                "seq": seq,
                "cmd": 2,
                "crc_ok": 1,
            }
            tp = f"{args.topic_root}/node/{args.node_id}/telemetry"
            client.publish(tp, json.dumps(telemetry, ensure_ascii=False), qos=0, retain=False)
            print(f"[PUB] {tp} {telemetry}")

            if inject:
                evt = {
                    "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                    "ts": now,
                    "node_id": args.node_id,
                    "level": "P2",
                    "anomaly_type": "inject_dist_drop_curr_spike",
                    "score": 0.86,
                    "threshold": 0.8,
                    "detail": {
                        "note": "simulated anomaly",
                        "dist_mm": telemetry["dist_mm"],
                        "curr_ma": telemetry["curr_ma"],
                    },
                    "ack": 0,
                }
                ep = f"{args.topic_root}/node/{args.node_id}/event"
                client.publish(ep, json.dumps(evt, ensure_ascii=False), qos=0, retain=False)
                print(f"[PUB] {ep} {evt}")

            seq = (seq + 1) & 0xFFFF
            time.sleep(max(0.02, args.interval_ms / 1000.0))
    finally:
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
