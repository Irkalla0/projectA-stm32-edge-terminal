# Project A CAN Upgrade Tunnel Protocol (Final)

This protocol transports existing `UPG_*` text commands through CAN frames.

## 1. CAN IDs

- Host -> Device: `0x321` (standard 11-bit)
- Device -> Host: `0x322` (standard 11-bit)

## 2. Frame Types

- `0x01` SEG: command segment
- `0x02` EOM: command end marker
- `0xA0` ACK: segment stream accepted and command executed
- `0xA1` NACK: segment stream rejected

## 3. Payload Layout

### SEG frame (`0x01`)

| Byte | Meaning |
|---|---|
| 0 | `0x01` |
| 1 | `seq` |
| 2 | `seg_len` (1..5) |
| 3 | `frag_idx` |
| 4..7 | ASCII segment bytes |

### EOM frame (`0x02`)

| Byte | Meaning |
|---|---|
| 0 | `0x02` |
| 1 | `seq` |
| 2 | `frag_count` |
| 3..7 | reserved |

### ACK/NACK frame

| Byte | Meaning |
|---|---|
| 0 | `0xA0` or `0xA1` |
| 1 | `seq` |
| 2 | status code |
| 3..7 | reserved |

## 4. Host Behavior

1. Split ASCII command (`UPG_*` line + `\n`) into up to 5-byte segments.
2. Send SEG frames in `frag_idx` order.
3. Send EOM frame with same `seq`.
4. Wait ACK. On NACK/timeout, retry command.
5. In `parallel` mode, fallback to UART after repeated CAN failures.

## 5. Device Behavior

1. Collect SEG frames by `seq`.
2. On EOM, reconstruct command line and run the same parser as UART.
3. Return ACK/NACK over CAN ID `0x322`.
