# Project A Final Audit Checklist

Version target: `v2.0.0-final`
Branch source: `codex/w25q128-integration`

## Capability Matrix

| Capability | Status | Primary implementation |
|---|---|---|
| 4-channel heterogeneous acquisition + threshold alarms | Implemented | `projectA_day1_sht30_mx/Core/Src/main.c` |
| Binary frame protocol + CRC16(Modbus) | Implemented | `projectA_day1_sht30_mx/Core/Src/main.c` |
| Dual UART fault tolerance + command interaction | Implemented | `projectA_day1_sht30_mx/Core/Src/main.c` |
| Bootloader + application dual-slot rollback flow | Implemented (workspace + protocol core) | `bootloader/`, `bootloader_f407/` |
| CAN + UART parallel upgrade + segmented retry | Implemented | `projectA_day1_sht30_mx/Core/Src/main.c`, `pc_tools/upgrade_client.py` |
| MQTT distributed aggregation + node offline detection | Implemented | `pc_tools/distributed_aggregator.py` |
| Rule engine + EWMA/Z-score + IsolationForest | Implemented | `pc_tools/analyze_and_forecast.py` |
| Holt-Winters short-term forecasting | Implemented | `pc_tools/analyze_and_forecast.py` |
| Python waveform viewer + firmware delivery + log export | Implemented | `pc_tools/uart_frame_viewer.py`, `pc_tools/upgrade_client.py` |

## Final Showcase Entry Points

- Top-level showcase: `README.md`
- Wiring: `docs/projectA_final_wiring.md`
- End-to-end runbook: `docs/projectA_final_runbook.md`
- CAN tunnel protocol: `docs/protocol/v2_upgrade_can_tunnel.md`
- One-page summary: `docs/projectA_one_page_summary.md`

## Release Gate (must pass before merge to main)

1. `py -m py_compile` succeeds for `pc_tools/*.py` touched by final release.
2. `tools/pack_fw.py inspect --strict` succeeds for final package.
3. M1-M6 dry-run commands print correctly in `tools/projectA_full_rollout.ps1`.
4. Root docs have no `TODO|待做|WIP|IN_PROGRESS` markers.
5. PR includes screenshots/log excerpts for serial + upgrade + distributed + analytics pipeline.

## Known Non-blocking Working Tree Items

The following pre-existing `.docx` files are not required for final code release and can be handled separately:

- `docs/projectA_rollout_master_plan.docx` (modified)
- `docs/ProjectA-final-template-style-v2.docx` (untracked)
- `docs/ProjectA-final-template-style.docx` (untracked)
- `docs/template_projectA_scheme.docx` (untracked)
- `docs/项目A_最终版.docx` (untracked)
