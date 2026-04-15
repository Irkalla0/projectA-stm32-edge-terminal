#!/usr/bin/env python3
"""
Project A distributed aggregator.

Merges:
- UART viewer CSV stream (tail mode)
- MQTT node telemetry/events

Outputs:
- telemetry CSV
- events CSV
- SQLite (telemetry/events tables)
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover
    mqtt = None


TELEMETRY_HEADERS = [
    "ts",
    "node_id",
    "temp_c",
    "hum_rh",
    "dist_mm",
    "curr_ma",
    "seq",
    "cmd",
    "crc_ok",
    "source",
]

EVENT_HEADERS = [
    "event_id",
    "ts",
    "node_id",
    "level",
    "anomaly_type",
    "score",
    "threshold",
    "detail",
    "ack",
    "source",
]


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _ensure_csv(path: Path, headers):
    path.parent.mkdir(parents=True, exist_ok=True)
    need_header = (not path.exists()) or path.stat().st_size == 0
    fp = path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fp, fieldnames=headers)
    if need_header:
        writer.writeheader()
        fp.flush()
    return fp, writer


def _ensure_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            node_id TEXT NOT NULL,
            temp_c REAL,
            hum_rh REAL,
            dist_mm REAL,
            curr_ma REAL,
            seq INTEGER,
            cmd INTEGER,
            crc_ok INTEGER,
            source TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            ts REAL NOT NULL,
            node_id TEXT NOT NULL,
            level TEXT,
            anomaly_type TEXT,
            score REAL,
            threshold REAL,
            detail TEXT,
            ack INTEGER DEFAULT 0,
            source TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


@dataclass
class NodeState:
    last_seen: float
    count: int = 0


@dataclass
class NodeTracker:
    states: Dict[str, NodeState] = field(default_factory=dict)

    def touch(self, node_id: str, now_ts: float):
        st = self.states.get(node_id)
        if st is None:
            self.states[node_id] = NodeState(last_seen=now_ts, count=1)
        else:
            st.last_seen = now_ts
            st.count += 1

    def snapshot(self, now_ts: float, timeout_s: float) -> Dict[str, Dict[str, object]]:
        out = {}
        for node_id, st in sorted(self.states.items()):
            idle = max(0.0, now_ts - st.last_seen)
            out[node_id] = {
                "count": st.count,
                "idle_s": idle,
                "online": idle <= timeout_s,
            }
        return out


class Aggregator:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.tele_fp, self.tele_writer = _ensure_csv(Path(args.out_telemetry).resolve(), TELEMETRY_HEADERS)
        self.evt_fp, self.evt_writer = _ensure_csv(Path(args.out_events).resolve(), EVENT_HEADERS)
        self.db = _ensure_db(Path(args.out_db).resolve())
        self.tracker = NodeTracker()
        self.online_state: Dict[str, bool] = {}
        self.serial_processed_rows = 0
        self.mqtt_client = None

    def close(self):
        try:
            if self.mqtt_client is not None:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
        except Exception:
            pass
        self.tele_fp.close()
        self.evt_fp.close()
        self.db.close()

    def write_telemetry(self, row: dict):
        now = time.time()
        ts = _to_float(row.get("ts", now), now)
        out = {
            "ts": ts,
            "node_id": str(row.get("node_id", "unknown")),
            "temp_c": row.get("temp_c", ""),
            "hum_rh": row.get("hum_rh", ""),
            "dist_mm": row.get("dist_mm", ""),
            "curr_ma": row.get("curr_ma", ""),
            "seq": _to_int(row.get("seq", ""), 0) if str(row.get("seq", "")).strip() else "",
            "cmd": _to_int(row.get("cmd", ""), 0) if str(row.get("cmd", "")).strip() else "",
            "crc_ok": _to_int(row.get("crc_ok", ""), 0) if str(row.get("crc_ok", "")).strip() else "",
            "source": str(row.get("source", "unknown")),
        }
        self.tele_writer.writerow(out)
        self.tele_fp.flush()
        self.db.execute(
            """
            INSERT INTO telemetry (ts,node_id,temp_c,hum_rh,dist_mm,curr_ma,seq,cmd,crc_ok,source)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                out["ts"],
                out["node_id"],
                _to_float(out["temp_c"], None),
                _to_float(out["hum_rh"], None),
                _to_float(out["dist_mm"], None),
                _to_float(out["curr_ma"], None),
                _to_int(out["seq"], None) if out["seq"] != "" else None,
                _to_int(out["cmd"], None) if out["cmd"] != "" else None,
                _to_int(out["crc_ok"], None) if out["crc_ok"] != "" else None,
                out["source"],
            ),
        )
        self.db.commit()
        self.tracker.touch(out["node_id"], ts)

    def write_event(self, row: dict):
        now = time.time()
        out = {
            "event_id": str(row.get("event_id", f"evt_{uuid.uuid4().hex[:12]}")),
            "ts": _to_float(row.get("ts", now), now),
            "node_id": str(row.get("node_id", "unknown")),
            "level": str(row.get("level", "P3")),
            "anomaly_type": str(row.get("anomaly_type", "unknown")),
            "score": _to_float(row.get("score", 0.0), 0.0),
            "threshold": _to_float(row.get("threshold", 0.0), 0.0),
            "detail": (
                json.dumps(row.get("detail", {}), ensure_ascii=False)
                if isinstance(row.get("detail"), (dict, list))
                else str(row.get("detail", ""))
            ),
            "ack": _to_int(row.get("ack", 0), 0),
            "source": str(row.get("source", "unknown")),
        }
        self.evt_writer.writerow(out)
        self.evt_fp.flush()
        self.db.execute(
            """
            INSERT INTO events (event_id,ts,node_id,level,anomaly_type,score,threshold,detail,ack,source)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                out["event_id"],
                out["ts"],
                out["node_id"],
                out["level"],
                out["anomaly_type"],
                out["score"],
                out["threshold"],
                out["detail"],
                out["ack"],
                out["source"],
            ),
        )
        self.db.commit()
        self.tracker.touch(out["node_id"], out["ts"])

    def ingest_serial_tail(self):
        if not self.args.serial_csv:
            return
        p = Path(self.args.serial_csv).resolve()
        if not p.exists():
            return
        with p.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) < self.serial_processed_rows:
            self.serial_processed_rows = 0
        new_rows = rows[self.serial_processed_rows :]
        self.serial_processed_rows = len(rows)

        for r in new_rows:
            if str(r.get("source", "")).strip() != "frame":
                continue
            self.write_telemetry(
                {
                    "ts": _to_float(r.get("host_ts", time.time()), time.time()),
                    "node_id": self.args.serial_node_id,
                    "temp_c": r.get("temp_c", ""),
                    "hum_rh": r.get("hum_rh", ""),
                    "dist_mm": r.get("dist_mm", ""),
                    "curr_ma": r.get("curr_ma", ""),
                    "seq": r.get("seq", ""),
                    "cmd": r.get("cmd", ""),
                    "crc_ok": r.get("crc_ok", ""),
                    "source": "uart",
                }
            )

    def init_mqtt(self):
        if not self.args.enable_mqtt:
            print("[INFO] MQTT disabled by flag")
            return
        if mqtt is None:
            print("[WARN] paho-mqtt not installed, MQTT input disabled")
            return

        client = mqtt.Client(client_id=self.args.mqtt_client_id)

        def on_connect(c, _u, _flags, rc):
            if rc != 0:
                print(f"[WARN] MQTT connect failed: rc={rc}")
                return
            t1 = f"{self.args.topic_root}/node/+/telemetry"
            t2 = f"{self.args.topic_root}/node/+/event"
            c.subscribe(t1, qos=0)
            c.subscribe(t2, qos=0)
            print(f"[INFO] MQTT subscribed: {t1}, {t2}")

        def on_message(_c, _u, msg):
            topic = msg.topic
            payload = msg.payload.decode("utf-8", errors="replace").strip()
            try:
                obj = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                print(f"[WARN] MQTT payload not JSON: {topic} {payload[:80]}")
                return

            parts = topic.split("/")
            node_id = obj.get("node_id")
            if not node_id and len(parts) >= 4:
                node_id = parts[2]

            if topic.endswith("/telemetry"):
                obj["node_id"] = node_id or "unknown"
                obj["source"] = "mqtt"
                self.write_telemetry(obj)
            elif topic.endswith("/event"):
                obj["node_id"] = node_id or "unknown"
                obj["source"] = "mqtt"
                self.write_event(obj)

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self.args.mqtt_host, self.args.mqtt_port, keepalive=30)
        client.loop_start()
        self.mqtt_client = client
        print(f"[INFO] MQTT connected: {self.args.mqtt_host}:{self.args.mqtt_port}")

    def run(self):
        self.init_mqtt()
        t0 = time.time()
        next_stat = t0 + self.args.status_interval_s
        while True:
            now = time.time()
            self.ingest_serial_tail()
            if now >= next_stat:
                snap = self.tracker.snapshot(now, self.args.node_timeout_s)
                for node_id, st in snap.items():
                    is_online = bool(st["online"])
                    prev_online = self.online_state.get(node_id)
                    if prev_online is None:
                        self.online_state[node_id] = is_online
                        continue
                    if prev_online != is_online:
                        self.online_state[node_id] = is_online
                        self.write_event(
                            {
                                "event_id": f"evt_node_{uuid.uuid4().hex[:12]}",
                                "ts": now,
                                "node_id": node_id,
                                "level": "P2" if not is_online else "P3",
                                "anomaly_type": "node_offline" if not is_online else "node_recovered",
                                "score": 1.0 if not is_online else 0.0,
                                "threshold": self.args.node_timeout_s,
                                "detail": {
                                    "idle_s": st["idle_s"],
                                    "count": st["count"],
                                    "online": is_online,
                                },
                                "ack": 0,
                                "source": "aggregator",
                            }
                        )
                online = [k for k, v in snap.items() if v["online"]]
                offline = [k for k, v in snap.items() if not v["online"]]
                print(
                    f"[STAT] nodes={len(snap)} online={online} offline={offline} "
                    f"telemetry_csv={self.args.out_telemetry}"
                )
                next_stat = now + self.args.status_interval_s

            if self.args.runtime_s > 0 and (now - t0) >= self.args.runtime_s:
                print("[INFO] runtime reached, exiting")
                return
            time.sleep(self.args.poll_interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Project A distributed aggregator")
    parser.add_argument("--enable-mqtt", action="store_true", help="enable MQTT ingestion")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-client-id", default="projectA-aggregator")
    parser.add_argument("--topic-root", default="projectA")
    parser.add_argument("--serial-csv", default="", help="tail uart viewer csv")
    parser.add_argument("--serial-node-id", default="stm32_core")
    parser.add_argument("--out-telemetry", default="D:/codex/project A/logs/distributed_telemetry.csv")
    parser.add_argument("--out-events", default="D:/codex/project A/logs/distributed_events.csv")
    parser.add_argument("--out-db", default="D:/codex/project A/logs/distributed.db")
    parser.add_argument("--node-timeout-s", type=float, default=30.0)
    parser.add_argument("--status-interval-s", type=float, default=5.0)
    parser.add_argument("--poll-interval-s", type=float, default=0.5)
    parser.add_argument("--runtime-s", type=float, default=0.0, help="0 means forever")
    args = parser.parse_args()

    agg = Aggregator(args)
    try:
        agg.run()
    finally:
        agg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
