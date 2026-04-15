# Project A Release Note

Release: `v2.0.0-final`
Date: 2026-04-15

## Highlights

Project A reaches final showcase delivery with end-to-end implementation from embedded acquisition through distributed analytics.

### Firmware
- Added CAN1 parallel upgrade tunnel while preserving UART upgrade compatibility.
- Implemented segmented command ingestion and ACK/NACK response for CAN transport.
- Finalized dual-channel command path (USART1 primary + USART2 backup).
- Added real-sensor-first acquisition path for temperature/humidity/distance/current.
- Kept binary telemetry frame protocol with CRC16(Modbus) and alarm frame support.

### Upgrade and Boot
- Delivered dual-slot upgrade flow with activation/confirmation/rollback semantics.
- Added independent bootloader workspace (`bootloader_f407`) aligned with shared protocol core.
- Preserved W25Q128 boot-state persistence interface and workflow.

### Host and Data Pipeline
- Added unified upgrade client (`pc_tools/upgrade_client.py`) with `uart|can|parallel` transport modes.
- Added viewer upgrade panel integration in `uart_frame_viewer.py`.
- Enhanced distributed aggregator with node offline/recovery event output.
- Delivered analytics pipeline with anomaly detection and Holt-Winters forecasting.

### Documentation
- Replaced root docs with final showcase entry points.
- Added final wiring and final runbook docs.
- Added CAN tunnel protocol specification.
- Moved legacy planning drafts to `docs/archive/`.

## Compatibility

- Existing `UPG_*` command semantics over UART remain compatible.
- Existing logs/CSV processing path remains supported.

## Upgrade Notes

1. Rebuild firmware package with `tools/make_app_bin.py` + `tools/pack_fw.py`.
2. Use `pc_tools/upgrade_client.py --transport parallel` for final recommended path.
3. For UART-only environment, pass `--transport uart`.
4. For CAN-only lab validation, pass `--transport can` and set CAN adapter parameters.
