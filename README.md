# Project A Final Edition

STM32F407 multi-sensor edge terminal with full-chain delivery:

- 4-channel heterogeneous acquisition + threshold alarms
- custom binary frame protocol + CRC16(Modbus)
- dual-UART fault-tolerant command channel
- dual-slot upgrade + boot state rollback (W25Q128)
- CAN + UART parallel upgrade with retry and auto fallback
- MQTT multi-node aggregation + offline/recovery identification
- rule engine + EWMA/Z-score + IsolationForest anomaly detection
- Holt-Winters short-term forecasting
- Python host waveform viewer + firmware delivery + log export

## 1. Repository Layout

- `projectA_day1_sht30_mx/`: application firmware project
- `bootloader/`: shared boot policy/protocol core
- `bootloader_f407/`: independent bootloader implementation workspace
- `pc_tools/`: host tools (viewer, upgrader, analytics, distributed aggregator)
- `tools/`: packaging and rollout scripts
- `docs/projectA_final_wiring.md`: full hardware wiring and bring-up
- `docs/projectA_final_runbook.md`: end-to-end execution playbook
- `docs/protocol/v2_upgrade_can_tunnel.md`: CAN upgrade tunnel frame definition

## 2. Frozen Interfaces

- UART commands: `GET_VER GET_CAP GET_FLASH GET_BOOTSTATE GET_PERIOD GET_THR GET_THR2 SET_* UPG_*`
- MQTT topics:
  - `projectA/node/{node_id}/telemetry`
  - `projectA/node/{node_id}/event`
  - `projectA/cmd/{node_id}`
- Telemetry schema: `ts,node_id,temp_c,hum_rh,dist_mm,curr_ma,seq,crc_ok,source`
- Event schema: `event_id,ts,node_id,level,anomaly_type,score,threshold,detail,ack`

## 3. 5-Min Quick Start

### 3.1 Install Python dependencies

```powershell
py -m pip install pyserial pandas numpy scikit-learn statsmodels paho-mqtt python-can
```

### 3.2 Build and pack firmware

```powershell
py "D:\codex\project A\tools\make_app_bin.py" --elf "D:\codex\project A\projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf" --out "D:\codex\project A\build\v2\app.bin"
py "D:\codex\project A\tools\pack_fw.py" pack --input "D:\codex\project A\build\v2\app.bin" --version 2.0.0 --board STM32F407ZGTx --out-dir "D:\codex\project A\build\v2"
py "D:\codex\project A\tools\pack_fw.py" inspect --input "D:\codex\project A\build\v2\upgrade_package.bin" --strict
```

### 3.3 Launch viewer and upgrade

```powershell
py "D:\codex\project A\pc_tools\uart_frame_viewer.py" --port auto --baud 115200 --csv "D:\codex\project A\logs\run.csv"

py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport parallel --port COM6 --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm --abort-on-fail
```

### 3.4 Run analytics and distributed pipeline

```powershell
py "D:\codex\project A\pc_tools\analyze_and_forecast.py" "D:\codex\project A\logs\day11_demo_run.csv" "D:\codex\project A\logs\day14_demo.csv" --out-dir "D:\codex\project A\build\analysis"

py "D:\codex\project A\pc_tools\distributed_aggregator.py" --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 --serial-csv "D:\codex\project A\logs\run.csv"
```

## 4. Full Runbook and Wiring

- execution: `docs/projectA_final_runbook.md`
- wiring: `docs/projectA_final_wiring.md`
- one-page summary: `docs/projectA_one_page_summary.md`
- resume bullets: `docs/resume_projectA_bullets.md`

## 5. Delivery Notes

- Main branch is maintained as final showcase state.
- Historical planning drafts are stored under `docs/archive/`.
- Offline/recovery node events are persisted in `logs/distributed_events.csv` and `logs/distributed.db`.
