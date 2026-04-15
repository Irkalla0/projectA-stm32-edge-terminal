# PC Tools Final Handbook

## Core tools

- `uart_frame_viewer.py`: real-time waveform, command panel, upgrade panel, CSV export
- `upgrade_client.py`: unified firmware upgrade (`uart`, `can`, `parallel`)
- `uart_upgrade_client.py`: legacy UART upgrader (kept for compatibility)
- `distributed_aggregator.py`: UART + MQTT merge, SQLite persistence, node offline/recovery events
- `mqtt_node_sim.py`: distributed node simulator
- `analyze_and_forecast.py`: anomaly detection + forecasting pipeline
- `v1_regression_check.py`: CRC and stability regression checks
- `v2_reliability_report.py`: upgrade reliability report generation

## Unified upgrade examples

```powershell
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport uart --port COM6 --activate --confirm

py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport can --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm

py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport parallel --port COM6 --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm --abort-on-fail
```

## Distributed aggregation

```powershell
py "D:\codex\project A\pc_tools\distributed_aggregator.py" --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 --serial-csv "D:\codex\project A\logs\run.csv"
```

## Analytics and forecast

```powershell
py "D:\codex\project A\pc_tools\analyze_and_forecast.py" "D:\codex\project A\logs\run.csv" --out-dir "D:\codex\project A\build\analysis"
```
