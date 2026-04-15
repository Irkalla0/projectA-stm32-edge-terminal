#include "../include/boot_storage.h"
#include "../include/boot_cfg.h"
#include "../../bootloader/include/pa_boot_policy.h"

/*
 * This file provides a storage abstraction for boot state.
 * Hardware-specific SPI erase/program/read primitives should be implemented
 * in board porting layer and called from this module.
 */

static uint32_t crc32_update(uint32_t crc, const uint8_t *data, uint16_t len)
{
  uint16_t i = 0;
  uint8_t b = 0;
  crc = ~crc;
  for (i = 0; i < len; ++i)
  {
    crc ^= data[i];
    for (b = 0; b < 8; ++b)
    {
      if (crc & 1U)
        crc = (crc >> 1) ^ 0xEDB88320U;
      else
        crc >>= 1;
    }
  }
  return ~crc;
}

int boot_storage_read(pa_boot_state_t *state)
{
  (void)state;
  /* Porting hook: read primary + backup pages, validate CRC, choose newer seq */
  return -1;
}

int boot_storage_write(const pa_boot_state_t *state)
{
  pa_boot_state_t copy;
  uint32_t crc = 0;

  if (state == 0)
    return -1;

  copy = *state;
  copy.crc32 = 0;
  crc = crc32_update(0xFFFFFFFFU, (const uint8_t *)&copy, (uint16_t)sizeof(copy));
  copy.crc32 = crc;

  /* Porting hook: write to primary and backup pages with erase/program/verify */
  return 0;
}

int boot_storage_read_jedec(uint32_t *jedec_id)
{
  if (jedec_id == 0)
    return -1;
  /* Porting hook: read W25 JEDEC via SPI */
  *jedec_id = 0;
  return 0;
}
