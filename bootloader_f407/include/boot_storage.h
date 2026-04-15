#ifndef BOOT_STORAGE_H
#define BOOT_STORAGE_H

#include <stdint.h>
#include "../../bootloader/include/pa_boot_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

int boot_storage_read(pa_boot_state_t *state);
int boot_storage_write(const pa_boot_state_t *state);
int boot_storage_read_jedec(uint32_t *jedec_id);

#ifdef __cplusplus
}
#endif

#endif
