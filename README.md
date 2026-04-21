# 项目A 最终版（中文版）

> English version: `README_EN.md`

基于 STM32F407 的多传感边缘监测终端（最终展示版），覆盖完整工程链路：

- 4 路异构采集 + 阈值告警
- 自定义二进制帧协议 + CRC16(Modbus)
- 双串口容错命令链路
- 双镜像升级 + Boot State 回滚（W25Q128）
- CAN + UART 并行升级（重传与自动降级）
- MQTT 多节点汇聚 + 掉线/恢复识别
- 规则引擎 + EWMA/Z-score + IsolationForest 异常检测
- Holt-Winters 短期趋势预测
- Python 上位机波形显示 + 固件下发 + 日志导出

## 1. 仓库结构

- `projectA_day1_sht30_mx/`：应用固件工程
- `bootloader/`：共享启动策略/协议核心
- `bootloader_f407/`：独立 Bootloader 工作区
- `pc_tools/`：上位机工具（Viewer、升级、分析、分布式汇聚）
- `tools/`：打包、联调、发布脚本
- `docs/projectA_final_wiring.md`：最终接线与上电联调
- `docs/projectA_final_runbook.md`：最终全链路执行手册
- `docs/protocol/v2_upgrade_can_tunnel.md`：CAN 升级隧道协议定义

## 2. 冻结接口

- UART 指令：`GET_VER GET_CAP GET_FLASH GET_BOOTSTATE GET_PERIOD GET_THR GET_THR2 SET_* UPG_*`
- MQTT 主题：
  - `projectA/node/{node_id}/telemetry`
  - `projectA/node/{node_id}/event`
  - `projectA/cmd/{node_id}`
- 遥测字段：`ts,node_id,temp_c,hum_rh,dist_mm,curr_ma,seq,crc_ok,source`
- 事件字段：`event_id,ts,node_id,level,anomaly_type,score,threshold,detail,ack`

## 3. 5 分钟快速开始

### 3.1 安装 Python 依赖

```powershell
py -m pip install pyserial pandas numpy scikit-learn statsmodels paho-mqtt python-can
```

### 3.2 构建并打包固件

```powershell
py "D:\codex\project A\tools\make_app_bin.py" --elf "D:\codex\project A\projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf" --out "D:\codex\project A\build\v2\app.bin"
py "D:\codex\project A\tools\pack_fw.py" pack --input "D:\codex\project A\build\v2\app.bin" --version 2.0.0 --board STM32F407ZGTx --out-dir "D:\codex\project A\build\v2"
py "D:\codex\project A\tools\pack_fw.py" inspect --input "D:\codex\project A\build\v2\upgrade_package.bin" --strict
```

### 3.3 启动 Viewer 并执行升级

```powershell
py "D:\codex\project A\pc_tools\uart_frame_viewer.py" --port auto --baud 115200 --csv "D:\codex\project A\logs\run.csv"

py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport parallel --port COM6 --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm --abort-on-fail
```

### 3.4 运行分析与分布式汇聚

```powershell
py "D:\codex\project A\pc_tools\analyze_and_forecast.py" "D:\codex\project A\logs\day11_demo_run.csv" "D:\codex\project A\logs\day14_demo.csv" --out-dir "D:\codex\project A\build\analysis"

py "D:\codex\project A\pc_tools\distributed_aggregator.py" --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 --serial-csv "D:\codex\project A\logs\run.csv"
```

## 4. 最终文档入口

- 执行手册：`docs/projectA_final_runbook.md`
- 接线手册：`docs/projectA_final_wiring.md`
- 一页总结：`docs/projectA_one_page_summary.md`
- 简历要点：`docs/resume_projectA_bullets.md`

## 5. 发布说明

- `main` 分支维护为最终展示态。
- 历史计划稿统一归档到 `docs/archive/`。
- 分布式离线/恢复事件落盘在 `logs/distributed_events.csv` 与 `logs/distributed.db`。
