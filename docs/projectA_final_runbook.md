# 项目A 最终版执行手册（Runbook）

更新日期：2026-04-15

本手册用于执行最终版完整链路：固件构建、升级、分布式汇聚、异常检测与趋势预测。

## 1. 前置条件

- 硬件已按 `docs/projectA_final_wiring.md` 完成接线
- 已安装 Python 依赖：

```powershell
py -m pip install pyserial pandas numpy scikit-learn statsmodels paho-mqtt python-can
```

- MQTT Broker 已启动（如 `mosquitto -v` 或系统服务）

## 2. 构建与打包

```powershell
py "D:\codex\project A\tools\make_app_bin.py" --elf "D:\codex\project A\projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf" --out "D:\codex\project A\build\v2\app.bin"

py "D:\codex\project A\tools\pack_fw.py" pack --input "D:\codex\project A\build\v2\app.bin" --version 2.0.0 --board STM32F407ZGTx --out-dir "D:\codex\project A\build\v2"

py "D:\codex\project A\tools\pack_fw.py" inspect --input "D:\codex\project A\build\v2\upgrade_package.bin" --strict
```

## 3. 烧录后校验 + W25 校验

```powershell
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd GET_FLASH --expect id=0xEF4018
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd BOOT_SAVE
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd BOOT_LOAD
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --baud 115200 --cmd GET_BOOTSTATE
```

## 4. 并行升级（CAN + UART）

```powershell
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport parallel --port COM6 --baud 115200 --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm --abort-on-fail
```

链路降级选项：

```powershell
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport uart --port COM6 --activate --confirm
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport can --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm
```

## 5. Viewer 与日志导出

```powershell
py "D:\codex\project A\pc_tools\uart_frame_viewer.py" --port auto --baud 115200 --csv "D:\codex\project A\logs\run.csv"
```

- 用波形面板观察实时遥测。
- 用升级面板直接推送升级包。

## 6. 分布式汇聚

终端 A：

```powershell
py "D:\codex\project A\pc_tools\distributed_aggregator.py" --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 --serial-csv "D:\codex\project A\logs\run.csv"
```

终端 B：

```powershell
py "D:\codex\project A\pc_tools\mqtt_node_sim.py" --node-id esp32_sim_01 --runtime-s 180
```

终端 C：

```powershell
py "D:\codex\project A\pc_tools\mqtt_node_sim.py" --node-id esp32_sim_02 --seed 99 --runtime-s 180
```

输出文件：

- `logs/distributed_telemetry.csv`
- `logs/distributed_events.csv`
- `logs/distributed.db`

## 7. 异常检测 + 预测

```powershell
py "D:\codex\project A\pc_tools\analyze_and_forecast.py" "D:\codex\project A\logs\run.csv" --out-dir "D:\codex\project A\build\analysis"
```

期望输出：

- `build/analysis/unified_telemetry.csv`
- `build/analysis/features_with_scores.csv`
- `build/analysis/anomaly_events.csv`
- `build/analysis/forecast.csv`
- `build/analysis/analysis_report.txt`

## 8. 分阶段一键执行

```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m1 -Port COM6 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m2 -Port COM6 -Transport parallel -CanInterface slcan -CanChannel COM8 -CanBitrate 500000 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m3 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m4 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m5 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m6 -Execute
```
