# Project A One-Page Summary

## 项目定位
项目A是一个基于 STM32F407 的边缘监测与可升级系统，目标是把单机采集终端升级为可扩展的分布式智能监测方案。

## 核心能力
- 多源采集与告警：温湿度、距离、电流统一采样并输出告警帧。
- 在线升级：UART 分包升级 + 双槽状态管理 + 激活确认流程。
- 持久化状态：接入 W25Q128，支持 Boot State 保存与恢复。
- 数据智能：异常检测（规则+统计+模型）与短期预测（Holt-Winters）。
- 分布式扩展：STM32 串口流与 ESP32 MQTT 节点流统一汇聚。

## 技术栈
- 固件：STM32F407, FreeRTOS, HAL, SPI/UART/I2C
- 上位机：Python (`pyserial`, `pandas`, `numpy`, `scikit-learn`, `statsmodels`, `paho-mqtt`)
- 协议与中间件：UART 自定义协议, MQTT, Mosquitto
- 存储与证据：CSV + SQLite + 升级日志

## 关键结果
- 升级主流程已稳定跑通：`BEGIN -> DATA -> END -> ACTIVATE -> CONFIRM`
- 串口链路支持健康诊断、重试控制和低速字符发送抗干扰
- 形成“硬件接线-脚本执行-日志验证-GitHub同步”的完整闭环

## 交付文件
- 全量实施手册：`docs/projectA_all_in_one_execution_and_wiring_2026-04-14.md`
- 总计划：`docs/projectA_master_plan_full_sync_2026-04-14.md`
- 阶段执行脚本：`tools/projectA_full_rollout.ps1`

