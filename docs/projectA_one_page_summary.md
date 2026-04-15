# Project A One-Page Summary

## 项目定位
Project A 是一个面向实战交付的 STM32F407 边缘监测与可靠升级系统，目标是把单机采集终端升级为可扩展的分布式智能监测平台。

## 核心能力
- 四路异构采集与阈值告警：温度、湿度、距离、电流。
- 自定义二进制帧协议：`0xAA55 + cmd + len + seq + ts + payload + CRC16`。
- 双串口容错：`USART1(PA9/PA10)` 主口 + `USART2(PA2/PA3)` 备口。
- 双镜像升级与回滚：A/B slot + Boot State + W25Q128 持久化。
- 并行升级链路：CAN + UART 并行，支持重传与自动降级。
- 分布式汇聚：STM32 串口流 + MQTT 节点流统一入库。
- 异常检测与预测：规则引擎 + EWMA/Z-score + IsolationForest + Holt-Winters。

## 技术栈
- 固件：STM32F407, FreeRTOS, HAL, I2C/SPI/UART/CAN
- 上位机：Python (`pyserial`, `python-can`, `pandas`, `numpy`, `scikit-learn`, `statsmodels`, `paho-mqtt`)
- 通信：UART, CAN, MQTT (Mosquitto)
- 存储：CSV + SQLite

## 交付入口
- 总入口：`README.md`
- 完整接线：`docs/projectA_final_wiring.md`
- 完整执行：`docs/projectA_final_runbook.md`
- 简历条目：`docs/resume_projectA_bullets.md`
