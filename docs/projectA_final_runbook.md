# Project A Final Runbook

Updated: 2026-04-15

This runbook executes the complete final-delivery path: firmware, upgrade, distributed aggregation, anomaly detection, and forecasting.

## 1. Prerequisites

- Hardware wired per `docs/projectA_final_wiring.md`
- Python deps installed:

```powershell
py -m pip install pyserial pandas numpy scikit-learn statsmodels paho-mqtt python-can
```

- MQTT broker running (`mosquitto -v` or service mode)

## 2. Build and Package

```powershell
py "D:\codex\project A\tools\make_app_bin.py" --elf "D:\codex\project A\projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf" --out "D:\codex\project A\build\v2\app.bin"

py "D:\codex\project A\tools\pack_fw.py" pack --input "D:\codex\project A\build\v2\app.bin" --version 2.0.0 --board STM32F407ZGTx --out-dir "D:\codex\project A\build\v2"

py "D:\codex\project A\tools\pack_fw.py" inspect --input "D:\codex\project A\build\v2\upgrade_package.bin" --strict
```

## 3. Flash + W25 Validation

```powershell
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd GET_FLASH --expect id=0xEF4018
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd BOOT_SAVE
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd BOOT_LOAD
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd GET_BOOTSTATE
```

## 4. Parallel Upgrade (CAN + UART)

```powershell
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport parallel --port COM6 --baud 115200 --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm --abort-on-fail
```

Fallback transport options:

```powershell
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport uart --port COM6 --activate --confirm
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport can --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm
```

## 5. Viewer + Log Export

```powershell
py "D:\codex\project A\pc_tools\uart_frame_viewer.py" --port auto --baud 115200 --csv "D:\codex\project A\logs\run.csv"
```

- Use waveform panel for telemetry.
- Use upgrade panel in viewer for direct package push.

## 6. Distributed Aggregation

Terminal A:

```powershell
py "D:\codex\project A\pc_tools\distributed_aggregator.py" --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 --serial-csv "D:\codex\project A\logs\run.csv"
```

Terminal B:

```powershell
py "D:\codex\project A\pc_tools\mqtt_node_sim.py" --node-id esp32_sim_01 --runtime-s 180
```

Terminal C:

```powershell
py "D:\codex\project A\pc_tools\mqtt_node_sim.py" --node-id esp32_sim_02 --seed 99 --runtime-s 180
```

Outputs:

- `logs/distributed_telemetry.csv`
- `logs/distributed_events.csv`
- `logs/distributed.db`

## 7. Anomaly + Forecast

```powershell
py "D:\codex\project A\pc_tools\analyze_and_forecast.py" "D:\codex\project A\logs\run.csv" --out-dir "D:\codex\project A\build\analysis"
```

Expected files:

- `build/analysis/unified_telemetry.csv`
- `build/analysis/features_with_scores.csv`
- `build/analysis/anomaly_events.csv`
- `build/analysis/forecast.csv`
- `build/analysis/analysis_report.txt`

## 8. One-command Stage Execution

```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m1 -Port COM6 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m2 -Port COM6 -Transport parallel -CanInterface slcan -CanChannel COM8 -CanBitrate 500000 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m3 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m4 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m5 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m6 -Execute
```
