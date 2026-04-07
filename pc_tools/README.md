# PC Tools Handbook (V1 + V2 + Analytics + Distributed)

本目录聚焦四类能力：

1. V1 基线回归
2. V2 升级可靠性
3. 数据分析与短期预测
4. 分布式传感网络聚合（UART + MQTT）

---

## 1) 依赖安装

```powershell
py -m pip install pyserial pandas numpy scikit-learn statsmodels paho-mqtt
```

可选依赖说明：

- 缺 `scikit-learn`：`analyze_and_forecast.py` 会跳过 IsolationForest，仍可运行。
- 缺 `statsmodels`：预测退化为“最后值延拓”，仍可运行。
- 缺 `paho-mqtt`：MQTT 相关脚本不可用，UART 分析脚本不受影响。

---

## 2) V1 基线回归

脚本：`v1_regression_check.py`

用途：

- 计算 CRC 通过率、运行时长、序号连续性
- 可选解析命令日志，给出命令响应健康度
- 输出：文本报告 + JSON 指标

示例：

```powershell
py "D:\codex\project A\pc_tools\v1_regression_check.py" `
  "D:\codex\project A\logs\day11_demo_run.csv" `
  --min-crc-pass-rate 0.99 `
  --min-duration-s 600 `
  --max-seq-jump-ratio 0.02
```

---

## 3) V2 升级可靠性报告

脚本：`v2_reliability_report.py`

用途：

- 生成统一的 V2 升级可靠性报告模板（R1~R7）
- 可读入 JSON 结果自动填表

示例：

```powershell
py "D:\codex\project A\pc_tools\v2_reliability_report.py"
```

带结果输入：

```powershell
py "D:\codex\project A\pc_tools\v2_reliability_report.py" `
  --results-json "D:\codex\project A\build\analysis\v2_results.json"
```

---

## 4) 数据分析 + 异常检测 + 预测

脚本：`analyze_and_forecast.py`

流水线：

`采集 -> 清洗 -> 特征 -> 异常评分 -> 预测 -> 报告`

输出：

- `unified_telemetry.csv`
- `features_with_scores.csv`
- `anomaly_events.csv`
- `forecast.csv`
- `analysis_report.txt`
- `analysis_summary.json`

示例：

```powershell
py "D:\codex\project A\pc_tools\analyze_and_forecast.py" `
  "D:\codex\project A\logs\day11_demo_run.csv" `
  "D:\codex\project A\logs\day14_demo.csv" `
  --resample-seconds 30 `
  --horizon-steps 60 `
  --out-dir "D:\codex\project A\build\analysis"
```

---

## 5) 分布式聚合（UART + MQTT）

脚本：`distributed_aggregator.py`

功能：

- 订阅 MQTT 多节点数据
- 尾读 `uart_frame_viewer.py` 的 CSV
- 统一写入：
  - `logs/distributed_telemetry.csv`
  - `logs/distributed_events.csv`
  - `logs/distributed.db`
- 输出节点在线/掉线状态

启动聚合器（MQTT + UART）：

```powershell
py "D:\codex\project A\pc_tools\distributed_aggregator.py" `
  --enable-mqtt `
  --mqtt-host 127.0.0.1 `
  --mqtt-port 1883 `
  --serial-csv "D:\codex\project A\logs\run.csv"
```

只做 UART 汇聚（无 MQTT）：

```powershell
py "D:\codex\project A\pc_tools\distributed_aggregator.py" `
  --serial-csv "D:\codex\project A\logs\run.csv"
```

---

## 6) MQTT 节点仿真

脚本：`mqtt_node_sim.py`

用途：

- 在没到齐硬件前模拟 ESP32 节点遥测
- 定时注入异常事件，便于压测异常检测链路

示例（节点1）：

```powershell
py "D:\codex\project A\pc_tools\mqtt_node_sim.py" `
  --node-id esp32_sim_01 `
  --runtime-s 120
```

示例（节点2）：

```powershell
py "D:\codex\project A\pc_tools\mqtt_node_sim.py" `
  --node-id esp32_sim_02 `
  --seed 99 `
  --runtime-s 120
```

---

## 7) 今日最小闭环（零新增硬件）

1. 跑 `uart_frame_viewer.py` 采集 `logs/run.csv`
2. 跑 `distributed_aggregator.py --serial-csv logs/run.csv` 聚合入库
3. 跑 `analyze_and_forecast.py logs/run.csv` 生成日报与异常事件
4. 跑 `v1_regression_check.py logs/run.csv` 生成 V1 回归报告
5. 跑 `v2_reliability_report.py` 生成 V2 验收模板

