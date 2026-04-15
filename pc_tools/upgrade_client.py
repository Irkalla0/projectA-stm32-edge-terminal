#!/usr/bin/env python3
"""
Project A unified upgrader.

Supports:
- UART text channel (compatible with existing UPG_* protocol)
- CAN segmented text tunnel (for parallel transport with auto fallback)
- Parallel mode: prefer CAN, fallback to UART after repeated CAN failures
"""

from __future__ import annotations

import argparse
import re
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import serial
import serial.tools.list_ports

try:
    import can
except Exception:  # pragma: no cover
    can = None


MAGIC = b"PAFW"
HEADER_FMT = "<4sHHIIHHHI16s12s10s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

NACK_RE = re.compile(r"^UPG_NACK\s+(\w+)\s+(\S+)")
ACK_BEGIN_RE = re.compile(r"^UPG_ACK BEGIN off=0$")
ACK_DATA_RE = re.compile(r"^UPG_ACK DATA off=(\d+)$")
ACK_END_RE = re.compile(r"^UPG_ACK END$")
ACK_ACTIVATE_RE = re.compile(r"^UPG_ACK ACTIVATE$")
ACK_CONFIRM_RE = re.compile(r"^UPG_ACK CONFIRM$")

CAP_RE = re.compile(r"^CAP:upgrade_uart=(\d+),max_chunk=(\d+),dual_slot=(\d+)$")
STATUS_RE = re.compile(r"^UPG_STATUS:([^,]+),off=(\d+),err=(.+)$")
BOOT_RE = re.compile(r"^BOOT:active=.*$")

CAN_PKT_SEG = 0x01
CAN_PKT_EOM = 0x02
CAN_PKT_ACK = 0xA0
CAN_PKT_NACK = 0xA1
CAN_SEG_PAYLOAD = 5


@dataclass
class FirmwarePackage:
    version: str
    image_size: int
    image_crc32: int
    payload: bytes
    board: str
    git_sha: str


class UartLink:
    def __init__(self, port: str, baud: int, read_timeout: float):
        self.ser, self.port = self._open_serial(port, baud, read_timeout)
        self.read_timeout = read_timeout

    @staticmethod
    def _list_candidate_ports(preferred: str) -> list[str]:
        if preferred.lower() != "auto":
            return [preferred]
        ports = list(serial.tools.list_ports.comports())
        ch340 = sorted([p.device for p in ports if "CH340" in (p.description or "").upper()])
        others = sorted(
            [p.device for p in ports if p.device not in ch340 and p.device.upper().startswith("COM")]
        )
        return ch340 + others

    def _open_serial(self, preferred: str, baud: int, timeout: float) -> tuple[serial.Serial, str]:
        for port in self._list_candidate_ports(preferred):
            try:
                ser = serial.Serial(port, baudrate=baud, timeout=timeout)
                return ser, port
            except serial.SerialException:
                continue
        raise RuntimeError(f"No usable UART port for --port {preferred}")

    def close(self) -> None:
        self.ser.close()

    def send_cmd(self, cmd: str, char_delay_ms: int = 0, preflush_newlines: int = 0) -> None:
        payload = (cmd + "\n").encode("ascii")
        if preflush_newlines > 0:
            self.ser.write(b"\n" * preflush_newlines)
            self.ser.flush()
            time.sleep(0.02)

        if char_delay_ms <= 0:
            self.ser.write(payload)
            self.ser.flush()
        else:
            delay_s = char_delay_ms / 1000.0
            for b in payload:
                self.ser.write(bytes([b]))
                self.ser.flush()
                time.sleep(delay_s)
        print(f"[UART TX] {cmd}")

    def wait_line(self, timeout_s: float) -> Optional[str]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            line = self.ser.readline().decode("utf-8", errors="replace").strip()
            if line:
                print(f"[UART RX] {line}")
                return line
        return None

    def wait_match(self, timeout_s: float, patterns: list[tuple[str, re.Pattern[str]]]):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            line = self.ser.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            print(f"[UART RX] {line}")
            for name, pat in patterns:
                m = pat.match(line)
                if m:
                    return name, m, line
        return None, None, None


class CanLink:
    def __init__(self, args: argparse.Namespace):
        if can is None:
            raise RuntimeError("python-can is not installed. pip install python-can")

        kwargs = {
            "interface": args.can_interface,
            "channel": args.can_channel,
            "bitrate": args.can_bitrate,
        }
        try:
            self.bus = can.Bus(**kwargs)
        except TypeError:
            # Backward-compatible python-can API.
            self.bus = can.interface.Bus(
                bustype=args.can_interface,
                channel=args.can_channel,
                bitrate=args.can_bitrate,
            )
        self.tx_id = args.can_tx_id
        self.rx_id = args.can_rx_id
        self.seq = 0

    def close(self) -> None:
        self.bus.shutdown()

    def _send_frame(self, data: bytes, timeout: float = 0.2) -> None:
        msg = can.Message(
            arbitration_id=self.tx_id,
            is_extended_id=False,
            data=data,
        )
        self.bus.send(msg, timeout=timeout)

    def send_cmd(self, cmd: str, ack_timeout: float) -> None:
        seq = self.seq & 0xFF
        self.seq = (self.seq + 1) & 0xFF

        raw = cmd.encode("ascii") + b"\n"
        chunk_count = (len(raw) + CAN_SEG_PAYLOAD - 1) // CAN_SEG_PAYLOAD
        frag_idx = 0
        for i in range(0, len(raw), CAN_SEG_PAYLOAD):
            chunk = raw[i : i + CAN_SEG_PAYLOAD]
            frame = bytearray(8)
            frame[0] = CAN_PKT_SEG
            frame[1] = seq
            frame[2] = len(chunk)
            frame[3] = frag_idx & 0xFF
            frame[4 : 4 + len(chunk)] = chunk
            self._send_frame(bytes(frame))
            frag_idx += 1

        end = bytearray(8)
        end[0] = CAN_PKT_EOM
        end[1] = seq
        end[2] = chunk_count & 0xFF
        self._send_frame(bytes(end))
        print(f"[CAN TX] {cmd}")

        deadline = time.time() + ack_timeout
        while time.time() < deadline:
            msg = self.bus.recv(timeout=0.05)
            if msg is None:
                continue
            if msg.is_extended_id:
                continue
            if msg.arbitration_id != self.rx_id:
                continue
            if len(msg.data) < 2:
                continue
            typ = msg.data[0]
            rx_seq = msg.data[1]
            if rx_seq != seq:
                continue
            if typ == CAN_PKT_ACK:
                code = msg.data[2] if len(msg.data) > 2 else 0
                print(f"[CAN RX] ACK seq={seq} code={code}")
                return
            if typ == CAN_PKT_NACK:
                code = msg.data[2] if len(msg.data) > 2 else 0
                raise RuntimeError(f"CAN NACK seq={seq} code={code}")

        raise TimeoutError(f"CAN ACK timeout for seq={seq}")


class TransportRouter:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.uart: Optional[UartLink] = None
        self.can: Optional[CanLink] = None
        self.active = args.transport
        self.can_fail_count = 0

        if args.transport in ("uart", "parallel"):
            self.uart = UartLink(args.port, args.baud, args.read_timeout)
            print(f"[INFO] UART opened: {self.uart.port} @ {args.baud}")
        if args.transport in ("can", "parallel"):
            self.can = CanLink(args)
            print(
                f"[INFO] CAN opened: {args.can_interface}:{args.can_channel} "
                f"bitrate={args.can_bitrate} tx=0x{args.can_tx_id:X} rx=0x{args.can_rx_id:X}"
            )

        if args.transport == "parallel":
            self.active = "can"

    def close(self) -> None:
        if self.uart is not None:
            self.uart.close()
        if self.can is not None:
            self.can.close()

    def send_cmd(self, cmd: str) -> None:
        if self.active == "uart":
            assert self.uart is not None
            self.uart.send_cmd(
                cmd,
                char_delay_ms=self.args.ctrl_char_delay_ms,
                preflush_newlines=self.args.preflush_newlines,
            )
            return

        if self.active == "can":
            assert self.can is not None
            try:
                self.can.send_cmd(cmd, ack_timeout=self.args.can_ack_timeout)
                self.can_fail_count = 0
                return
            except Exception as exc:
                self.can_fail_count += 1
                print(f"[WARN] CAN send failed ({self.can_fail_count}/{self.args.can_fail_threshold}): {exc}")
                if self.args.transport == "parallel" and self.uart is not None and self.can_fail_count >= self.args.can_fail_threshold:
                    self.active = "uart"
                    print("[WARN] Switch transport CAN -> UART")
                    self.uart.send_cmd(
                        cmd,
                        char_delay_ms=self.args.ctrl_char_delay_ms,
                        preflush_newlines=self.args.preflush_newlines,
                    )
                    return
                raise

        raise RuntimeError(f"Unsupported active transport: {self.active}")

    def query_optional_uart(self, cmd: str, pattern: re.Pattern[str], timeout_s: float, retries: int) -> Optional[str]:
        if self.uart is None:
            return None
        for idx in range(max(1, retries)):
            self.uart.send_cmd(
                cmd,
                char_delay_ms=self.args.ctrl_char_delay_ms,
                preflush_newlines=self.args.preflush_newlines,
            )
            name, _m, line = self.uart.wait_match(timeout_s, [("ok", pattern)])
            if name == "ok":
                return line
            print(f"[WARN] UART query timeout: {cmd} ({idx + 1}/{max(1, retries)})")
        return None

    def expect_ack_uart(self, phase: str, ack_pattern: re.Pattern[str], timeout_s: float):
        if self.uart is None:
            return None
        name, m, _line = self.uart.wait_match(
            timeout_s,
            [("ack", ack_pattern), ("nack", NACK_RE)],
        )
        if name == "ack":
            return m
        if name == "nack" and m is not None:
            raise RuntimeError(f"{phase} failed: {m.group(1)} {m.group(2)}")
        raise TimeoutError(f"{phase} timeout")


def read_package(pkg_path: Path) -> FirmwarePackage:
    blob = pkg_path.read_bytes()
    if len(blob) < HEADER_SIZE:
        raise ValueError(f"Package too small: {len(blob)}")

    (
        magic,
        header_size,
        _header_ver,
        image_size,
        image_crc,
        vmaj,
        vmin,
        vpat,
        _build_unix,
        board_raw,
        sha_raw,
        _reserved,
    ) = struct.unpack(HEADER_FMT, blob[:HEADER_SIZE])

    if magic != MAGIC:
        raise ValueError(f"Bad magic: {magic!r}")
    if header_size != HEADER_SIZE:
        raise ValueError(f"Bad header size: {header_size}, expect {HEADER_SIZE}")

    payload = blob[HEADER_SIZE : HEADER_SIZE + image_size]
    if len(payload) != image_size:
        raise ValueError(f"Payload truncated: {len(payload)} vs {image_size}")

    calc_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if calc_crc != image_crc:
        raise ValueError(f"Payload CRC mismatch: calc=0x{calc_crc:08X}, header=0x{image_crc:08X}")

    return FirmwarePackage(
        version=f"{vmaj}.{vmin}.{vpat}",
        image_size=image_size,
        image_crc32=image_crc,
        payload=payload,
        board=board_raw.rstrip(b"\x00").decode("ascii", errors="ignore"),
        git_sha=sha_raw.rstrip(b"\x00").decode("ascii", errors="ignore"),
    )


def run_upgrade(args: argparse.Namespace) -> int:
    pkg = read_package(Path(args.pkg).resolve())
    print(
        "[INFO] Package:",
        f"ver={pkg.version}",
        f"size={pkg.image_size}",
        f"crc=0x{pkg.image_crc32:08X}",
        f"board={pkg.board}",
        f"git={pkg.git_sha}",
    )

    if args.dry_run:
        print("[INFO] Dry-run enabled, package check complete.")
        return 0

    router = TransportRouter(args)
    try:
        if router.uart is not None:
            router.query_optional_uart("GET_VER", re.compile(r"^VER:app=.*"), args.ack_timeout, args.query_retries)
            cap_line = router.query_optional_uart("GET_CAP", CAP_RE, args.ack_timeout, args.query_retries)
            router.query_optional_uart("GET_BOOTSTATE", BOOT_RE, args.ack_timeout, args.query_retries)
            router.query_optional_uart("UPG_STATUS", STATUS_RE, args.ack_timeout, args.query_retries)
        else:
            cap_line = None

        chunk_size = max(1, min(args.chunk, 128))
        if cap_line:
            m = CAP_RE.match(cap_line)
            if m:
                chunk_size = min(chunk_size, int(m.group(2)))
        print(f"[INFO] Chunk size: {chunk_size}")

        router.send_cmd(f"UPG_BEGIN {pkg.version} {pkg.image_size} 0x{pkg.image_crc32:08X}")
        if router.active == "uart":
            router.expect_ack_uart("UPG_BEGIN", ACK_BEGIN_RE, args.ack_timeout)

        payload = pkg.payload
        total = len(payload)
        offset = 0
        while offset < total:
            chunk = payload[offset : offset + chunk_size]
            chunk_crc = zlib.crc32(chunk) & 0xFFFFFFFF
            cmd = f"UPG_DATA {offset} {chunk.hex().upper()} 0x{chunk_crc:08X}"
            if router.active == "uart":
                router.uart.send_cmd(
                    cmd,
                    char_delay_ms=args.data_char_delay_ms,
                    preflush_newlines=args.preflush_newlines,
                )
                m = router.expect_ack_uart(f"UPG_DATA@{offset}", ACK_DATA_RE, args.ack_timeout)
                next_off = int(m.group(1))
                if next_off != offset + len(chunk):
                    raise RuntimeError(f"Offset mismatch: ack={next_off} expected={offset + len(chunk)}")
                offset = next_off
            else:
                router.send_cmd(cmd)
                offset += len(chunk)

            pct = (offset * 100.0) / total
            print(f"[INFO] Progress: {offset}/{total} ({pct:.1f}%)")
            if args.chunk_delay_ms > 0:
                time.sleep(args.chunk_delay_ms / 1000.0)

        router.send_cmd("UPG_END")
        if router.active == "uart":
            router.expect_ack_uart("UPG_END", ACK_END_RE, args.ack_timeout)

        if args.activate:
            router.send_cmd("UPG_ACTIVATE")
            if router.active == "uart":
                router.expect_ack_uart("UPG_ACTIVATE", ACK_ACTIVATE_RE, args.ack_timeout)

        if args.confirm:
            router.send_cmd("UPG_CONFIRM")
            if router.active == "uart":
                router.expect_ack_uart("UPG_CONFIRM", ACK_CONFIRM_RE, args.ack_timeout)

        if router.uart is not None:
            router.query_optional_uart("GET_BOOTSTATE", BOOT_RE, args.ack_timeout, args.query_retries)
            router.query_optional_uart("UPG_STATUS", STATUS_RE, args.ack_timeout, args.query_retries)

        print("[OK] Upgrade flow completed")
        return 0
    except Exception as exc:
        print(f"[ERR] {exc}")
        if args.abort_on_fail:
            try:
                router.send_cmd("UPG_ABORT")
            except Exception as abort_exc:
                print(f"[WARN] UPG_ABORT failed: {abort_exc}")
        return 2
    finally:
        router.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Project A unified UART/CAN upgrader")
    p.add_argument("--pkg", required=True, help="path to upgrade_package.bin")
    p.add_argument("--transport", choices=["uart", "can", "parallel"], default="parallel")

    p.add_argument("--port", default="auto", help="UART COM port or auto")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--read-timeout", type=float, default=0.2)
    p.add_argument("--ack-timeout", type=float, default=2.0)
    p.add_argument("--query-retries", type=int, default=3)
    p.add_argument("--chunk", type=int, default=128)
    p.add_argument("--chunk-delay-ms", type=int, default=0)
    p.add_argument("--ctrl-char-delay-ms", type=int, default=0)
    p.add_argument("--data-char-delay-ms", type=int, default=0)
    p.add_argument("--preflush-newlines", type=int, default=0)

    p.add_argument("--can-interface", default="slcan", help="python-can interface, e.g. slcan/pcan/socketcan")
    p.add_argument("--can-channel", default="COM8", help="python-can channel, e.g. COM8 or can0")
    p.add_argument("--can-bitrate", type=int, default=500000)
    p.add_argument("--can-tx-id", type=lambda x: int(x, 0), default=0x321)
    p.add_argument("--can-rx-id", type=lambda x: int(x, 0), default=0x322)
    p.add_argument("--can-ack-timeout", type=float, default=0.8)
    p.add_argument("--can-fail-threshold", type=int, default=3)

    p.add_argument("--activate", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--abort-on-fail", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.chunk < 1 or args.chunk > 128:
        raise SystemExit("--chunk must be in range 1~128")
    if args.confirm and not args.activate:
        raise SystemExit("--confirm requires --activate")
    return run_upgrade(args)


if __name__ == "__main__":
    raise SystemExit(main())
