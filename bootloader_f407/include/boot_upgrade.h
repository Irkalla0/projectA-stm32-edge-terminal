#ifndef BOOT_UPGRADE_H
#define BOOT_UPGRADE_H

#include <stdint.h>
#include "../../bootloader/include/pa_boot_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

void boot_upgrade_session_reset(void);
int boot_upgrade_begin(uint32_t image_size, uint32_t image_crc32, uint8_t target_slot);
int boot_upgrade_feed(uint32_t offset, const uint8_t *data, uint16_t len, uint32_t chunk_crc32);
int boot_upgrade_end(void);
int boot_upgrade_activate(pa_boot_state_t *state, uint8_t target_slot, uint32_t image_size, uint32_t image_crc32);
int boot_upgrade_confirm(pa_boot_state_t *state);
int boot_upgrade_fail_once(pa_boot_state_t *state, uint8_t max_attempts);

#ifdef __cplusplus
}
#endif

#endif
