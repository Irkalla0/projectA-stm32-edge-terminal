# Bootloader Workspace (V2)

This directory now contains the portable bootloader core for Project A V2.

## Current status (without external flash)

- Protocol/state binary layouts are defined in:
  - `include/pa_boot_protocol.h`
- Boot decision policy and state transitions are implemented in:
  - `include/pa_boot_policy.h`
  - `src/pa_boot_policy.c`
- Host-side simulation is available:
  - `../tools/boot_policy_sim.py`

## What we can do right now (W25Q not required)

1. Validate rollback transitions with local files:
   - create/set-pending/confirm/rollback using `tools/boot_state_tool.py`
   - simulate reboot decisions using `tools/boot_policy_sim.py`
2. Keep app-side UART upgrade protocol aligned (`GET_BOOTSTATE`, `UPG_*`).
3. Freeze memory map and boot metadata before wiring SPI NOR.

## Example local validation

```powershell
py "D:\codex\project A\tools\boot_state_tool.py" create `
  --out "D:\codex\project A\build\v2\boot_state.bin" `
  --active-slot A --pending-slot NONE

py "D:\codex\project A\tools\boot_state_tool.py" set-pending `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --slot B

py "D:\codex\project A\tools\boot_policy_sim.py" decide `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --max-attempts 3

py "D:\codex\project A\tools\boot_policy_sim.py" step `
  --input "D:\codex\project A\build\v2\boot_state.bin" `
  --max-attempts 3
```

## Next step after W25Q128 arrives

1. Add SPI NOR driver (`read/write/erase` primitives).
2. Persist `pa_boot_state_t` in redundant sectors/pages.
3. Map slot A/B image regions and implement image verify + jump.
4. Move `UPG_*` write path from app RAM mock to bootloader flash writer.
