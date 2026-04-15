#include "../include/boot_upgrade.h"
#include "../../bootloader/include/pa_boot_policy.h"

static uint32_t g_expected_size = 0;
static uint32_t g_expected_crc = 0;
static uint32_t g_received = 0;

void boot_upgrade_session_reset(void)
{
  g_expected_size = 0;
  g_expected_crc = 0;
  g_received = 0;
}

int boot_upgrade_begin(uint32_t image_size, uint32_t image_crc32, uint8_t target_slot)
{
  (void)target_slot;
  if (image_size == 0)
    return -1;
  g_expected_size = image_size;
  g_expected_crc = image_crc32;
  g_received = 0;
  return 0;
}

int boot_upgrade_feed(uint32_t offset, const uint8_t *data, uint16_t len, uint32_t chunk_crc32)
{
  (void)data;
  (void)chunk_crc32;
  if (offset != g_received)
    return -1;
  g_received += len;
  if (g_received > g_expected_size)
    return -1;
  return 0;
}

int boot_upgrade_end(void)
{
  if (g_received != g_expected_size)
    return -1;
  return 0;
}

int boot_upgrade_activate(pa_boot_state_t *state, uint8_t target_slot, uint32_t image_size, uint32_t image_crc32)
{
  if (state == 0)
    return -1;
  pa_boot_set_slot_meta(state, target_slot, image_size, image_crc32);
  pa_boot_mark_pending(state, target_slot);
  return 0;
}

int boot_upgrade_confirm(pa_boot_state_t *state)
{
  if (state == 0)
    return -1;
  pa_boot_mark_confirm(state);
  return 0;
}

int boot_upgrade_fail_once(pa_boot_state_t *state, uint8_t max_attempts)
{
  if (state == 0)
    return -1;
  pa_boot_mark_fail_once(state, max_attempts);
  return 0;
}
