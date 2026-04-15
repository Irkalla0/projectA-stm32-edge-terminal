# PR To Main: Project A v2.0.0-final

## Title

`release(projectA): ship v2.0.0-final full-chain implementation`

## Summary

This PR promotes Project A to final showcase state, including complete firmware/host/documentation delivery:

- 4-channel heterogeneous acquisition with threshold alarms
- binary protocol with CRC16
- dual UART fault-tolerant command path
- dual-slot boot state rollback flow
- CAN + UART parallel upgrade with segmentation and fallback
- MQTT distributed aggregation with offline/recovery events
- anomaly detection (rule + EWMA/Z-score + IsolationForest)
- Holt-Winters forecast output
- waveform viewer + upgrade panel + log export

## Key Changes

1. Firmware
- Added CAN1 tunnel transport (`PA11/PA12`) with SEG/EOM/ACK/NACK flow.
- Preserved existing UART upgrade command semantics (`UPG_*`).
- Added real-sensor-first acquisition path for VL53L0X + INA219 with simulation fallback.

2. Host Tools
- Added `pc_tools/upgrade_client.py` unified upgrader (`uart|can|parallel`).
- Added upgrade panel integration in `pc_tools/uart_frame_viewer.py`.
- Added node offline/recovery event persistence in `pc_tools/distributed_aggregator.py`.

3. Architecture and Docs
- Added independent `bootloader_f407/` workspace.
- Rewrote showcase docs: final wiring, final runbook, protocol docs.
- Archived legacy planning drafts under `docs/archive/`.

## Validation

- Python syntax checks passed for touched host scripts.
- Rollout script stage dry-runs print expected command chain.
- Root final docs cleaned to showcase tone without plan-state markers.

## Risks / Notes

- CAN real-bus tests require USB2CAN + transceiver hardware and matching bitrate.
- Some legacy `.docx` templates are intentionally excluded from code release scope.

## Merge Strategy

- Merge commit into `main`.
- Create tag `v2.0.0-final`.
- Publish GitHub release with attached runbook and protocol references.
