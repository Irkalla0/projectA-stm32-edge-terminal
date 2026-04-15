#!/usr/bin/env python3
"""
Project A V2 reliability report generator.

Use this script to generate a markdown matrix for upgrade reliability cases.
Optional JSON input can pre-fill pass/fail/evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


DEFAULT_CASES = [
    {"id": "R1", "name": "正常升级+激活+确认", "target": "3轮连续通过"},
    {"id": "R2", "name": "Chunk CRC错误", "target": "设备返回UPG_NACK DATA E_CRC_CHUNK"},
    {"id": "R3", "name": "整包CRC错误", "target": "设备返回UPG_NACK END E_CRC_IMAGE"},
    {"id": "R4", "name": "非法版本/降级", "target": "设备拒绝激活并给出E_VER"},
    {"id": "R5", "name": "中断恢复（UPG_ABORT）", "target": "状态回到idle且系统可继续采集"},
    {"id": "R6", "name": "首启确认（UPG_CONFIRM）", "target": "pending清空且active切换"},
    {"id": "R7", "name": "试运行失败回滚（UPG_FAIL_ONCE）", "target": "达到阈值后last=rollback"},
]


def load_results(path: Path | None) -> Dict[str, dict]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, dict] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "id" in item:
                out[str(item["id"])] = item
    elif isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                out[str(k)] = v
    return out


def render_markdown(results: Dict[str, dict]) -> str:
    lines: List[str] = []
    lines.append("# Project A V2 升级可靠性报告")
    lines.append("")
    lines.append("| 用例ID | 用例名称 | 目标 | 结果 | 证据 |")
    lines.append("|---|---|---|---|---|")
    pass_cnt = 0
    total = len(DEFAULT_CASES)
    for c in DEFAULT_CASES:
        r = results.get(c["id"], {})
        result = str(r.get("result", "NOT_RECORDED"))
        evidence = str(r.get("evidence", "N/A"))
        if result.upper() in ("PASS", "OK", "通过"):
            pass_cnt += 1
        lines.append(f"| {c['id']} | {c['name']} | {c['target']} | {result} | {evidence} |")

    rate = (pass_cnt / total * 100.0) if total else 0.0
    lines.append("")
    lines.append(f"- 通过率：{pass_cnt}/{total} ({rate:.1f}%)")
    lines.append("- 建议结论：通过率>=90%可进入联调阶段；100%通过可进入演示版本。")
    lines.append("")
    lines.append("## 备注")
    lines.append("- 本报告可与 `uart_upgrade_client.py` 实际运行日志配套归档。")
    lines.append("- 建议每轮测试记录 firmware 版本号、包CRC、执行时间和串口端口。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate V2 reliability markdown report")
    parser.add_argument("--results-json", default="", help="optional JSON with case results")
    parser.add_argument(
        "--out",
        default="D:/codex/project A/build/analysis/v2_reliability_report.md",
    )
    args = parser.parse_args()

    results_path = Path(args.results_json).resolve() if args.results_json else None
    results = load_results(results_path)
    md = render_markdown(results)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"[INFO] Report generated: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
