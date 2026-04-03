# V2 Upgrade Tools

## 1) Build app.bin from ELF

```powershell
py "D:\codex\project A\tools\make_app_bin.py" `
  --elf "D:\codex\project A\projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf" `
  --out "D:\codex\project A\build\v2\app.bin"
```

## 2) Pack upgrade image

```powershell
py "D:\codex\project A\tools\pack_fw.py" pack `
  --input "D:\codex\project A\build\v2\app.bin" `
  --version 2.0.0 `
  --board STM32F407ZGTx `
  --out-dir "D:\codex\project A\build\v2"
```

## 3) Inspect package

```powershell
py "D:\codex\project A\tools\pack_fw.py" inspect `
  --input "D:\codex\project A\build\v2\upgrade_package.bin" `
  --strict
```

## 4) UART send package to MCU

```powershell
py "D:\codex\project A\pc_tools\uart_upgrade_client.py" `
  --pkg "D:\codex\project A\build\v2\upgrade_package.bin" `
  --port COM4 `
  --baud 115200 `
  --activate `
  --confirm `
  --abort-on-fail
```
