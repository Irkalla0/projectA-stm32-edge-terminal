#!/usr/bin/env python3
"""
Project A V1 baseline regression checker.

Checks:
- CRC pass rate
- run duration
- sequence continuity
- frame command coverage
- optional command/response health from viewer text log
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def _to_float(v: str, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v: str, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "y")


def _count_seq_jumps(seq_values: List[int]) -> int:
    if len(seq_values) < 2:
        return 0
    jumps = 0
    for prev, cur in zip(seq_values, seq_values[1:]):
        if ((prev + 1) & 0xFFFF) != (cur & 0xFFFF):
            jumps += 1
    return jumps


def _parse_cmd_health(log_path: Path) -> Dict[str, float]:
    """
    Optional health metric based on viewer/client logs.
    It's intentionally conservative: only checks whether response prefixes
    appeared after TXs in the same session log.
    """
    expected = {
        "GET_PERIOD": "PERIOD:",
        "GET_THR": "THR:",
        "GET_THR2": "THR2:",
        "GET_VER": "VER:",
        "GET_CAP": "CAP:",
        "UPG_STATUS": "UPG_STATUS:",
        "GET_BOOTSTATE": "BOOT:",
    }
    sent: Dict[str, int] = {k: 0 for k in expected}
    hit: Dict[str, int] = {k: 0 for k in expected}

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for ln in lines:
        s = ln.strip()
        if "[TX]" in s:
            for cmd in expected:
                if s.endswith(cmd) or f"[TX] {cmd}" in s:
                    sent[cmd] += 1
                    break
        for cmd, prefix in expected.items():
            if prefix in s:
                hit[cmd] += 1

    ratios: Dict[str, float] = {}
    for cmd in expected:
        if sent[cmd] <= 0:
            ratios[cmd] = -1.0
        else:
            ratios[cmd] = min(hit[cmd], sent[cmd]) / sent[cmd]
    return ratios


def _load_rows(paths: Iterable[Path]) -> List[dict]:
    rows: List[dict] = []
    for p in paths:
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if str(r.get("source", "")).strip() != "frame":
                    continue
                rows.append(r)
    rows.sort(key=lambda x: _to_float(x.get("host_ts", ""), 0.0))
    return rows


def analyze(
    csv_paths: List[Path],
    cmd_log: Path | None,
) -> Dict[str, object]:
    rows = _load_rows(csv_paths)
    total = len(rows)
    crc_ok = 0
    cmd_cnt: Dict[str, int] = {}
    seq_values: List[int] = []
    first_ts = None
    last_ts = None

    for r in rows:
        crc_ok += 1 if _truthy(r.get("crc_ok", "")) else 0
        cmd = str(r.get("cmd", "")).strip()
        if cmd:
            cmd_cnt[cmd] = cmd_cnt.get(cmd, 0) + 1
        seq_values.append(_to_int(r.get("seq", ""), 0))
        ts = _to_float(r.get("host_ts", ""), 0.0)
        if first_ts is None:
            first_ts = ts
        last_ts = ts

    duration_s = 0.0 if first_ts is None or last_ts is None else max(0.0, last_ts - first_ts)
    crc_pass_rate = 0.0 if total == 0 else (crc_ok / total)
    seq_jumps = _count_seq_jumps(seq_values)
    seq_jump_ratio = 0.0 if total <= 1 else seq_jumps / (total - 1)

    result: Dict[str, object] = {
        "total_frame": total,
        "crc_ok": crc_ok,
        "crc_pass_rate": crc_pass_rate,
        "duration_s": duration_s,
        "seq_jumps": seq_jumps,
        "seq_jump_ratio": seq_jump_ratio,
        "cmd_count": cmd_cnt,
        "cmd_health": {},
    }
    if cmd_log is not None and cmd_log.exists():
        result["cmd_health"] = _parse_cmd_health(cmd_log)
    return result


def verdict(
    result: Dict[str, object],
    min_crc_pass_rate: float,
    min_duration_s: float,
    max_seq_jump_ratio: float,
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    ok = True

    crc_rate = float(result["crc_pass_rate"])
    duration = float(result["duration_s"])
    seq_ratio = float(result["seq_jump_ratio"])

    if crc_rate < min_crc_pass_rate:
        ok = False
        reasons.append(
            f"CRC pass rate too low: {crc_rate:.4f} < {min_crc_pass_rate:.4f}"
        )
    if duration < min_duration_s:
        ok = False
        reasons.append(
            f"Duration too short: {duration:.1f}s < {min_duration_s:.1f}s"
        )
    if seq_ratio > max_seq_jump_ratio:
        ok = False
        reasons.append(
            f"Sequence jump ratio too high: {seq_ratio:.4f} > {max_seq_jump_ratio:.4f}"
        )

    return ok, reasons


def write_report(path: Path, result: Dict[str, object], ok: bool, reasons: List[str]) -> None:
    lines = []
    lines.append("=== Project A V1 Regression Report ===")
    lines.append(f"VERDICT: {'PASS' if ok else 'FAIL'}")
    lines.append(f"Total frame: {result['total_frame']}")
    lines.append(f"CRC pass: {result['crc_ok']}/{result['total_frame']} ({result['crc_pass_rate']:.4f})")
    lines.append(f"Duration(s): {result['duration_s']:.2f}")
    lines.append(f"Sequence jumps: {result['seq_jumps']} (ratio={result['seq_jump_ratio']:.4f})")
    lines.append(f"CMD count: {result['cmd_count']}")

    cmd_health = result.get("cmd_health", {})
    if isinstance(cmd_health, dict) and cmd_health:
        lines.append("Command response health (from optional text log):")
        for cmd, ratio in cmd_health.items():
            if ratio < 0:
                lines.append(f"  - {cmd}: N/A (not sent)")
            else:
                lines.append(f"  - {cmd}: {ratio:.2%}")

    if reasons:
        lines.append("Reasons:")
        for r in reasons:
            lines.append(f"- {r}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Project A V1 baseline regression checker")
    parser.add_argument("csv", nargs="+", help="one or more frame csv files")
    parser.add_argument("--cmd-log", default="", help="optional viewer/client text log")
    parser.add_argument("--min-crc-pass-rate", type=float, default=0.99)
    parser.add_argument("--min-duration-s", type=float, default=1800.0)
    parser.add_argument("--max-seq-jump-ratio", type=float, default=0.01)
    parser.add_argument(
        "--out-report",
        default="D:/codex/project A/build/analysis/v1_regression_report.txt",
    )
    parser.add_argument(
        "--out-json",
        default="D:/codex/project A/build/analysis/v1_regression_metrics.json",
    )
    args = parser.parse_args()

    csv_paths = [Path(x).resolve() for x in args.csv]
    cmd_log = Path(args.cmd_log).resolve() if args.cmd_log else None
    result = analyze(csv_paths, cmd_log)
    ok, reasons = verdict(
        result,
        min_crc_pass_rate=args.min_crc_pass_rate,
        min_duration_s=args.min_duration_s,
        max_seq_jump_ratio=args.max_seq_jump_ratio,
    )

    report_path = Path(args.out_report).resolve()
    json_path = Path(args.out_json).resolve()
    write_report(report_path, result, ok, reasons)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "verdict": "PASS" if ok else "FAIL",
                "metrics": result,
                "reasons": reasons,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[INFO] Report: {report_path}")
    print(f"[INFO] Metrics JSON: {json_path}")
    print(f"[INFO] VERDICT: {'PASS' if ok else 'FAIL'}")
    if reasons:
        for r in reasons:
            print(f"[WARN] {r}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
