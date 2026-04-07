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

The upgrader now queries `GET_BOOTSTATE` automatically before and after activate/confirm.

## 5) Prepare / inspect rollback boot state

Create an initial state blob:

```powershell
py "D:\codex\project A\tools\boot_state_tool.py" create `
  --out "D:\codex\project A\build\v2\boot_state.bin" `
  --active-slot A `
  --pending-slot NONE `
  --slot-a-size 0 `
  --slot-a-crc32 0x00000000 `
  --slot-b-size 0 `
  --slot-b-crc32 0x00000000
```

Inspect state integrity (`--strict` fails when CRC is invalid):

```powershell
py "D:\codex\project A\tools\boot_state_tool.py" inspect `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --strict
```

Mark slot B as pending and then confirm:

```powershell
py "D:\codex\project A\tools\boot_state_tool.py" set-pending `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --slot B

py "D:\codex\project A\tools\boot_state_tool.py" confirm `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --slot B
```

## 6) Simulate bootloader decision flow (no hardware required)

```powershell
py "D:\codex\project A\tools\boot_policy_sim.py" decide `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --max-attempts 3

py "D:\codex\project A\tools\boot_policy_sim.py" step `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --max-attempts 3
```
